"""Clause-level Q&A and risk summarisation (extractive, deterministic, no LLM needed).

Q&A pipeline
  1. plan_query     : resolve filing scope (ids / tickers / years), extract concepts, infer wanted sections
  2. retrieve       : gateway /search (query expanded with topic synonyms) -> sections with full text
  3. clause scoring : split sections into clauses, score by weighted concept coverage (+ section prior)
  4. greedy cover   : pick up to 3 clauses that together cover the question's concepts
  5. confidence     : covered concept weight / total weight; below QA_MIN_CONFIDENCE -> "I don't know."
Risk summary pipeline
  clauses of Risk Factors / Legal / MD&A -> gateway /tools/risk/score + topic taxonomy + severity cues
  -> rank -> topic-diverse top-N -> 3..5 cited bullets.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from . import config, retrieval, tools
from .text_utils import (GENERIC, RISK_CUES, STOPWORDS, _TOKEN, find_filing_ids, find_years,
                         normalize_filing_id, remove_ids, sentence, split_clauses, stem, stems, stems_match,
                         strip_refs, trim_words)
from .topics import TOPICS, detect_topics, label, topic_hits, topic_spans

IDK = "I don't know."
PRIOR = 0.15
MAX_ANSWER_SENTENCES = 3
RISK_SECTION = "Risk Factors"

SECTION_CUES = {
    "Financials": ("revenue", "margin", "gross", "profit", "income", "earning", "financial", "sale", "r&d", "ebitda"),
    "Business": ("segment", "market", "business", "operate", "product", "subscription", "channel", "offering"),
    "Legal Proceedings": ("legal", "proceeding", "lawsuit", "court", "sue", "suit", "litigation"),
    "MD&A": ("trend", "management", "md&a", "outlook", "opex", "discussion", "growth", "guidance", "investment"),
}
SECTION_ORDER = [RISK_SECTION, "Business", "Financials", "MD&A", "Legal Proceedings"]


class FilingNotFound(LookupError):
    pass


# ----------------------------------------------------------------------------- query planning
# Tiny lexical bridge for words that questions use but filings phrase differently.
ALIASES = {"growth": ("grew", "grow", "increase"), "driver": ("due", "driven", "because"),
           "decline": ("fell", "decrease", "drop"), "decrease": ("fell", "decline", "drop"),
           "increase": ("grew", "rose", "higher"), "sale": ("revenue",)}
SECTION_NAME_TOKENS = {"md&a": "MD&A", "mdna": "MD&A", "business": "Business", "financials": "Financials",
                       "legal": "Legal Proceedings", "proceeding": "Legal Proceedings",
                       "proceedings": "Legal Proceedings"}   # name a section; never content to match


@dataclass
class Concept:
    key: str
    kind: str            # "topic" | "token"
    weight: float
    stem: str = ""
    alts: Tuple[str, ...] = ()


@dataclass
class Plan:
    question: str
    fids: List[str] = field(default_factory=list)      # resolved explicit scope (<=3) -> per-filing mode
    candidates: Set[str] = field(default_factory=set)  # ticker/year restricted candidate set (search mode)
    unknown: List[str] = field(default_factory=list)
    concepts: List[Concept] = field(default_factory=list)
    intent: Set[str] = field(default_factory=set)      # section names the question points at
    risk_intent: bool = False

    @property
    def total_weight(self) -> float:
        return sum(c.weight for c in self.concepts)


def plan_query(question: str, filing_id: Optional[str] = None) -> Plan:
    known = retrieval.list_filings()
    known_set = set(known)
    tickers_known = {f.split("_")[0] for f in known}
    p = Plan(question=question)

    explicit = find_filing_ids(question)
    if filing_id:
        fid = normalize_filing_id(filing_id) or filing_id
        explicit = [fid] + [e for e in explicit if e != fid]
    for e in explicit:
        (p.fids if (e in known_set or not known_set) else p.unknown).append(e)
    tickers = {t for t in tickers_known if re.search(rf"\b{t}\b", question, re.I)}

    years = find_years(remove_ids(question))
    if not p.fids and not p.unknown:
        if tickers and years:
            p.fids = [f for f in known if f.split("_")[0] in tickers and f.split("_")[1] in years]
        elif tickers:
            p.candidates = {f for f in known if f.split("_")[0] in tickers}
        elif years:
            p.candidates = {f for f in known if f.split("_")[1] in years}
    p.fids = p.fids[:3]

    # ---- concepts
    q = strip_refs(question, tickers)
    spans = topic_spans(q)
    consumed = [s for v in spans.values() for s in v]
    for tid in spans:
        p.concepts.append(Concept(tid, "topic", 1.5))
        p.intent.add(RISK_SECTION)
    seen: Set[str] = set()
    for m in _TOKEN.finditer(q.lower()):
        if any(a <= m.start() < b for a, b in consumed):
            continue
        w = m.group(0)
        st = stem(w)
        if w in STOPWORDS or st in STOPWORDS or w in GENERIC or st in GENERIC or len(w) < 2:
            continue
        if w in SECTION_NAME_TOKENS:
            p.intent.add(SECTION_NAME_TOKENS[w])
            continue
        if w.startswith(RISK_CUES):
            p.risk_intent = True
            continue
        for sec, cues in SECTION_CUES.items():
            if any(w.startswith(c) for c in cues):
                p.intent.add(sec)
        if st not in seen:
            seen.add(st)
            p.concepts.append(Concept(st, "token", 1.0, st, ALIASES.get(st, ())))
    if p.risk_intent:
        p.intent.add(RISK_SECTION)
    if any(c.key == "litigation" for c in p.concepts) and not p.risk_intent:
        p.intent.add("Legal Proceedings")      # "any litigation?" -> also look at Legal; "litigation risks" -> Risk Factors
    return p


def search_query(plan: Plan) -> str:
    """Query string for the gateway: expand topic concepts into their keyword words."""
    words: List[str] = []
    for c in plan.concepts:
        if c.kind == "topic":
            for kw in TOPICS[c.key]["kw"]:
                words.extend(kw.split())
        else:
            words.append(c.stem)
            words.extend(c.alts)
    for sec in plan.intent:
        words.append({"Financials": "revenue", "Business": "segments", "Legal Proceedings": "litigation",
                      "MD&A": "management", RISK_SECTION: "risk"}[sec])
    return " ".join(dict.fromkeys(words)) or "risk"


# ----------------------------------------------------------------------------- clause scoring
@dataclass
class Clause:
    filing_id: str
    section: str
    text: str
    idx: int
    stems: List[str] = field(default_factory=list)
    topics: Dict[str, int] = field(default_factory=dict)


def clauses_from_hits(hits: List[Dict[str, Any]]) -> List[Clause]:
    out: List[Clause] = []
    seen: Set[Tuple[str, str]] = set()
    for h in hits:
        key = (h["filing_id"], h["section"])
        if key in seen:
            continue
        seen.add(key)
        for i, c in enumerate(split_clauses(retrieval.hit_text(h))):
            out.append(Clause(h["filing_id"], h["section"], c, i, stems(c), topic_hits(c)))
    return out


def matched_concepts(cl: Clause, plan: Plan) -> Set[int]:
    m: Set[int] = set()
    for i, c in enumerate(plan.concepts):
        if c.kind == "topic":
            if c.key in cl.topics:
                m.add(i)
        elif any(stems_match(a, s) for a in (c.stem,) + c.alts for s in cl.stems):
            m.add(i)
    return m


@dataclass
class Selection:
    clauses: List[Clause]
    covered: Set[int]
    confidence: float
    section_mode: bool = False


def select_evidence(clauses: List[Clause], plan: Plan, max_clauses: int = MAX_ANSWER_SENTENCES) -> Selection:
    if not clauses:
        return Selection([], set(), 0.0)
    if not plan.concepts:  # section-level question ("what are the key risks?")
        chosen: List[Clause] = []
        for sec in [s for s in SECTION_ORDER if s in plan.intent]:
            n = 2 if sec == RISK_SECTION else max_clauses   # risks: leave room for a one-line mention of the rest
            chosen += [c for c in clauses if c.section == sec][:n]
            if chosen:
                break
        return Selection(chosen[:max_clauses], set(), 0.7 if chosen else 0.0, section_mode=True)

    info = {id(c): matched_concepts(c, plan) for c in clauses}
    covered: Set[int] = set()
    chosen = []
    pool = [c for c in clauses if info[id(c)]]
    while pool and len(chosen) < max_clauses:
        def key(c: Clause):
            m = info[id(c)]
            gain = sum(plan.concepts[i].weight for i in m - covered)
            allw = sum(plan.concepts[i].weight for i in m)
            strength = sum(c.topics.get(plan.concepts[i].key, 1) if plan.concepts[i].kind == "topic" else 1 for i in m)
            density = len(m) / max(1, len(c.stems))          # prefer the more specific (shorter) clause on ties
            return (gain, PRIOR if c.section in plan.intent else 0.0, strength, density, allw, -clauses.index(c))
        best = max(pool, key=key)
        if key(best)[0] <= 0:
            break
        chosen.append(best)
        covered |= info[id(best)]
        pool.remove(best)
    conf = sum(plan.concepts[i].weight for i in covered) / plan.total_weight if plan.total_weight else 0.0
    return Selection(chosen, covered, round(conf, 3))


# ----------------------------------------------------------------------------- rendering
_KV = re.compile(r"^(?P<k>[^:]{2,60}):\s*(?P<v>.+?)\.?$")


def render_clause(c: Clause, prefix: bool = False) -> str:
    text = c.text
    if c.section == "Financials":
        m = _KV.match(text)
        if m:
            k = m.group("k").strip()
            k = k if k[:2].isupper() else k[0].lower() + k[1:]
            text = f"{c.filing_id}'s {k} is {m.group('v').strip()}"
            return sentence(text)
    s = sentence(text)
    return f"{c.filing_id}: {s}" if prefix else s


def _risk_context(clauses: List[Clause], chosen: List[Clause]) -> Optional[str]:
    used = {c.text for c in chosen}
    labels: List[str] = []
    for c in clauses:
        if c.section != RISK_SECTION or c.text in used:
            continue
        for t in detect_topics(c.text)[:1]:
            if label(t) not in labels:
                labels.append(label(t))
    if not labels:
        return None
    return "Other risks listed in the same section: " + "; ".join(l if l[:2].isupper() else l[0].lower() + l[1:] for l in labels[:4]) + "."


def _unmatched_note(plan: Plan, covered: Set[int]) -> Optional[str]:
    miss = [(TOPICS[c.key]["label"] if c.kind == "topic" else c.key) for i, c in enumerate(plan.concepts) if i not in covered]
    if not miss:
        return None
    return "The filing text does not address: " + ", ".join(miss[:3]) + "."


def _idk(conf: float, note: Optional[str] = None) -> Dict[str, Any]:
    return {"answer": IDK, "citations": [], "confidence": round(conf, 3), "evidence": [], "note": note}


def _cit(cs: List[Clause]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for c in cs:
        d = {"filing_id": c.filing_id, "section": c.section}
        if d not in out:
            out.append(d)
    return out


def _ev(cs: List[Clause]) -> List[Dict[str, str]]:
    return [{"filing_id": c.filing_id, "section": c.section, "text": c.text} for c in cs]


# ----------------------------------------------------------------------------- retrieval for Q&A
def _hits_for(plan: Plan, fid: Optional[str], top_k: int) -> List[Dict[str, Any]]:
    return retrieval.search(search_query(plan), filing_id=fid, top_k=top_k).get("results", [])


def _full_doc_hits(fid: str) -> List[Dict[str, Any]]:
    secs = retrieval.load_filing(fid) or {}
    return [{"filing_id": fid, "section": s, "score": 0.0, "snippet": t[:220], "text": t} for s, t in secs.items()]


def _select_for_filing(plan: Plan, fid: str) -> Tuple[Selection, List[Clause]]:
    clauses = clauses_from_hits(_hits_for(plan, fid, top_k=10))
    sel = select_evidence(clauses, plan)
    if sel.confidence < config.qa_min_confidence():  # recall fallback: scan the whole document
        clauses = clauses_from_hits(_full_doc_hits(fid))
        sel = select_evidence(clauses, plan)
    return sel, clauses


def retrieve(question: str, filing_id: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
    """Section ranking used for Precision@5: sections ordered by their best clause score."""
    plan = plan_query(question, filing_id)
    fids = plan.fids or [None]
    ranked: List[Tuple[float, str, str]] = []
    for fid in fids:
        hits = _hits_for(plan, fid, top_k=40 if fid is None else 10)
        if fid is None and plan.candidates:
            hits = [h for h in hits if h["filing_id"] in plan.candidates]
        clauses = clauses_from_hits(hits)
        by: Dict[Tuple[str, str], float] = {}
        for c in clauses:
            if plan.concepts:
                m = matched_concepts(c, plan)
                s = sum(plan.concepts[i].weight for i in m) / plan.total_weight if m else 0.0
            else:
                s = 0.5 if c.section in plan.intent else 0.0
            if s > 0:
                s += PRIOR if c.section in plan.intent else 0.0
            k = (c.filing_id, c.section)
            by[k] = max(by.get(k, 0.0), s)
        ranked += [(s, f, sec) for (f, sec), s in by.items() if s > 0]
    ranked.sort(key=lambda x: (-x[0], -int(x[1].split("_")[1]), x[1], SECTION_ORDER.index(x[2]) if x[2] in SECTION_ORDER else 9))
    return [{"filing_id": f, "section": sec, "score": round(s, 3)} for s, f, sec in ranked[:top_k]]


# ----------------------------------------------------------------------------- /qa
def answer_question(question: str, filing_id: Optional[str] = None) -> Dict[str, Any]:
    plan = plan_query(question, filing_id)
    min_conf = config.qa_min_confidence()

    if plan.unknown and not plan.fids:
        return _idk(0.0, f"Filing {', '.join(plan.unknown)} is not in the corpus.")
    if not plan.concepts and not plan.intent:
        return _idk(0.0, "The question has no searchable content.")

    # ---------- per-filing mode (explicit ids, or ticker x year)
    if plan.fids:
        results = []
        for fid in plan.fids:
            sel, clauses = _select_for_filing(plan, fid)
            results.append((fid, sel, clauses))
        if len(results) == 1:
            fid, sel, clauses = results[0]
            if not sel.clauses or sel.confidence < min_conf:
                return _idk(sel.confidence, "Low retrieval confidence; no clause covers the question." + (
                    f" ({', '.join(plan.unknown)} not in corpus)" if plan.unknown else ""))
            sents = [render_clause(c) for c in sel.clauses]
            extra = None if sel.section_mode else _unmatched_note(plan, sel.covered)
            if extra is None and (len(sents) < 2 or sel.section_mode) and sel.clauses[0].section == RISK_SECTION:
                extra = _risk_context(clauses, sel.clauses)
            if extra and len(sents) < MAX_ANSWER_SENTENCES:
                sents.append(extra)
            return {"answer": " ".join(sents[:MAX_ANSWER_SENTENCES]), "citations": _cit(sel.clauses),
                    "confidence": sel.confidence, "evidence": _ev(sel.clauses),
                    "note": f"{', '.join(plan.unknown)} not in corpus." if plan.unknown else None}
        answered = [(f, s) for f, s, _ in results if s.clauses and s.confidence >= min_conf]
        if not answered:
            return _idk(max(s.confidence for _, s, _ in results), "No filing in scope covers the question.")
        sents, used = [], []
        for fid, sel, _ in results:
            if sel.clauses and sel.confidence >= min_conf:
                sents.append(render_clause(sel.clauses[0], prefix=True))
                used.append(sel.clauses[0])
            else:
                sents.append(f"{fid}: no relevant disclosure found.")
        return {"answer": " ".join(sents[:MAX_ANSWER_SENTENCES]), "citations": _cit(used),
                "confidence": min(s.confidence for _, s in answered), "evidence": _ev(used), "note": None}

    # ---------- search mode (no explicit filing)
    if not plan.concepts:
        return _idk(0.0, "Please specify a filing id (e.g. ACMR_2023) for section-level questions.")
    hits = _hits_for(plan, None, top_k=60)
    if plan.candidates:
        hits = [h for h in hits if h["filing_id"] in plan.candidates]
    by_fid: Dict[str, List[Dict[str, Any]]] = {}
    for h in hits:
        by_fid.setdefault(h["filing_id"], []).append(h)
    best: Optional[Tuple[Any, str, Selection, List[Clause]]] = None
    for fid, hs in by_fid.items():
        cl = clauses_from_hits(hs)
        sel = select_evidence(cl, plan)
        if not sel.clauses:
            continue
        rank = (sel.confidence, int(fid.split("_")[1]), [-ord(ch) for ch in fid.split("_")[0]])
        if best is None or rank > best[0]:
            best = (rank, fid, sel, cl)
    if best is None or best[2].confidence < min_conf:
        return _idk(best[2].confidence if best else 0.0, "Low retrieval confidence across the corpus.")
    _, fid, sel, cl = best
    same = sorted({c.filing_id for c in cl_all(by_fid, sel) if c.filing_id != fid})
    sents = [render_clause(c) for c in sel.clauses]
    extra = _unmatched_note(plan, sel.covered)
    if extra is None and len(sents) < 2 and sel.clauses[0].section == RISK_SECTION:
        extra = _risk_context(cl, sel.clauses)
    if extra and len(sents) < MAX_ANSWER_SENTENCES:
        sents.append(extra)
    note = f"No filing specified; answered from {fid}."
    if same:
        note += f" Identical wording also appears in {len(same)} other filing(s)."
    return {"answer": " ".join(sents[:MAX_ANSWER_SENTENCES]), "citations": _cit(sel.clauses),
            "confidence": sel.confidence, "evidence": _ev(sel.clauses), "note": note}


def cl_all(by_fid: Dict[str, List[Dict[str, Any]]], sel: Selection) -> List[Clause]:
    """Clauses in other filings whose text is identical to a selected clause."""
    want = {(c.section, c.text) for c in sel.clauses}
    out: List[Clause] = []
    for fid, hs in by_fid.items():
        for c in clauses_from_hits(hs):
            if (c.section, c.text) in want:
                out.append(c)
    return out


# ----------------------------------------------------------------------------- /risksummary
SECTION_WEIGHT = {RISK_SECTION: 1.0, "Legal Proceedings": 0.6, "MD&A": 0.3}
SEVERITY = ("could", "may ", "adverse", "material", "disrupt", "loss", "penalt", "harm", "costly", "reduce",
            "delay", "increase", "compress", "trigger", "slow", "infring", "defend", "inquiry")
BOILERPLATE = re.compile(r"routine litigation|no proceedings are expected|not expected to have a material|other proceedings are routine", re.I)
MIN_BULLET_SCORE = 0.25


def _score_clause(text: str, section: str) -> Tuple[float, float]:
    api = tools.cached_risk_score(text)                 # mock /tools/risk/score (keyword density)
    norm_api = min(1.0, api / 0.3)
    low = text.lower() + " "
    sev = min(3, sum(1 for s in SEVERITY if s in low))
    s = norm_api + (0.5 if topic_hits(text) else 0.0) + 0.15 * sev
    if BOILERPLATE.search(text):
        s -= 0.6
    return SECTION_WEIGHT.get(section, 0.0) * s, api


def summarize_risks(filing_id: str, max_bullets: Optional[int] = None) -> Dict[str, Any]:
    fid = normalize_filing_id(filing_id) or filing_id
    secs = retrieval.load_filing(fid)
    if secs is None:
        raise FilingNotFound(fid)
    n = max(3, min(5, max_bullets or config.risk_bullets()))

    cands: List[Dict[str, Any]] = []
    order = 0
    for sec, weight in SECTION_WEIGHT.items():
        for c in split_clauses(secs.get(sec, "")):
            if len(c.split()) < 4:
                continue
            score, api = _score_clause(c, sec)
            cands.append({"text": c, "section": sec, "score": score, "api": api,
                          "topics": detect_topics(c), "order": order})
            order += 1
    cands.sort(key=lambda d: (-d["score"], d["order"]))

    chosen: List[Dict[str, Any]] = []
    covered: Set[str] = set()
    for d in cands:                                   # pass 1: confident, topic-diverse bullets
        if len(chosen) >= n or d["score"] < MIN_BULLET_SCORE:
            continue
        if d["topics"] and set(d["topics"]) <= covered:
            continue
        chosen.append(d)
        covered |= set(d["topics"])
    for d in cands:                                   # pass 2: guarantee at least 3 bullets
        if len(chosen) >= 3:
            break
        if d not in chosen and d["section"] == RISK_SECTION:
            chosen.append(d)

    warning = None
    if len(chosen) < 3:
        warning = "Fewer than 3 risk clauses found in this filing."
    bullets = [{
        "text": trim_words(sentence(d["text"]), 20),
        "topic": d["topics"][0] if d["topics"] else None,
        "topic_label": label(d["topics"][0]) if d["topics"] else None,
        "section": d["section"], "filing_id": fid, "score": round(d["score"], 3),
    } for d in chosen]
    return {"filing_id": fid, "summary": [b["text"] for b in bullets],
            "citations": [{"filing_id": fid, "section": b["section"]} for b in bullets],
            "bullets": bullets, "warning": warning}
