"""Tokenising, stemming, filing-id parsing and clause splitting."""
import re
from typing import List, Set, Tuple

STOPWORDS = set("""a an the and or of to in on for with by at from as is are was were be been being do does did
what which who whom how why when where that this these those it its their there any all about into than then has have
had can could would should may might will we our you your i me my s tell give please also more most much many some
such other another per vs versus between within across over under""".split())

# Question words that carry no content for matching.
GENERIC = set("""key main major top biggest principal primary mentioned mention mentions listed list describe describes
discuss discussed discusses explain summarize summary overview show say says said identify highlight regarding facing
face faces faced company companies filing filings annual report reports according state states change changes
changed impact impacts affect affects related relate percent percentage ratio pct intensity spend spending spent amount large larger big high higher low lower size regulation regulations section sections compare compared comparison differ difference differences disclose discloses disclosed include includes included
involved involve involves exposed status situation whether anything something information details detail current currently""".split())

# Words that signal *what kind of section* the user wants rather than content to match.
RISK_CUES = ("risk", "threat", "exposure", "vulnerab", "danger", "concern", "challeng", "uncertaint")

_TOKEN = re.compile(r"[a-z0-9]+(?:&[a-z0-9]+)?(?:-[a-z0-9]+)*")
_ID_UPPER = re.compile(r"\b([A-Z]{2,6})[\s_-]?((?:19|20)\d{2})\b")
_ID_JOINED = re.compile(r"\b([A-Za-z]{2,6})[_-]((?:19|20)\d{2})\b")
_NOT_TICKERS = {"FY", "Q", "H", "IN", "OF", "ON", "AT", "BY", "TO", "FROM", "YEAR"}
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_FY = re.compile(r"\bFY[\s-]?(\d{2})\b", re.I)


def tokenize(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


def stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith(("ches", "shes", "xes", "zes")):
        return w[:-2]
    if len(w) > 5 and w.endswith("sses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def stems(text: str) -> List[str]:
    return [stem(t) for t in tokenize(text)]


def stems_match(a: str, b: str) -> bool:
    """Equal, or sharing a long common prefix (operate~operation, compliance~compliant)."""
    if a == b:
        return True
    if min(len(a), len(b)) < 6:
        return False
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 6 and n / min(len(a), len(b)) >= 0.75


def normalize_filing_id(s: str):
    m = _ID_JOINED.search(s) or _ID_UPPER.search(s)
    if not m or m.group(1).upper() in _NOT_TICKERS:
        return None
    return f"{m.group(1).upper()}_{m.group(2)}"


def find_filing_ids(text: str) -> List[str]:
    """Explicit ids like ACMR-2023, ACMR_2023, 'ACMR 2023' (upper-case ticker only for the spaced form)."""
    out: List[str] = []
    for rx in (_ID_JOINED, _ID_UPPER):
        for m in rx.finditer(text):
            if m.group(1).upper() in _NOT_TICKERS:
                continue
            fid = f"{m.group(1).upper()}_{m.group(2)}"
            if fid not in out:
                out.append(fid)
    return out


def find_years(text: str) -> List[str]:
    ys = list(dict.fromkeys(_YEAR.findall(text)))
    for m in _FY.finditer(text):
        y = "20" + m.group(1)
        if y not in ys:
            ys.append(y)
    return ys


def remove_ids(text: str) -> str:
    """Blank out explicit filing ids only (not arbitrary 'word YEAR' pairs such as 'from 2022')."""
    return _ID_UPPER.sub(" ", _ID_JOINED.sub(" ", text))


def strip_refs(text: str, tickers: Set[str]) -> str:
    """Remove filing ids, years and known tickers so they don't become content concepts."""
    t = _ID_JOINED.sub(" ", text)
    t = _ID_UPPER.sub(" ", t)
    t = _FY.sub(" ", t)
    t = _YEAR.sub(" ", t)
    for tk in tickers:
        t = re.sub(rf"\b{re.escape(tk)}(?:'s)?\b", " ", t, flags=re.I)
    return t


_ABBR = ("U.S", "Inc", "Corp", "Ltd", "No", "e.g", "i.e", "vs", "approx")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z$0-9\"(])")


def split_clauses(text: str) -> List[str]:
    """Bullets -> one clause each; prose -> sentences."""
    clauses: List[str] = []
    buf: List[str] = []

    def flush():
        if buf:
            clauses.append(" ".join(buf).strip())
            buf.clear()

    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            flush()
            continue
        if re.match(r"^([-*\u2022]|\d+[.)])\s+", s):
            flush()
            buf.append(re.sub(r"^([-*\u2022]|\d+[.)])\s+", "", s))
        elif buf:
            buf.append(s)
        else:
            buf.append(s)
    flush()

    out: List[str] = []
    for c in clauses:
        parts = _SENT_SPLIT.split(c)
        merged: List[str] = []
        for p in parts:
            if merged and merged[-1].rstrip(".").endswith(_ABBR):
                merged[-1] += " " + p
            else:
                merged.append(p)
        out.extend(x.strip() for x in merged if x.strip())
    return out


def sentence(text: str) -> str:
    t = text.strip().rstrip(";,")
    if not t:
        return t
    t = t[0].upper() + t[1:]
    return t if t[-1] in ".!?" else t + "."


def trim_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    cut = " ".join(words[:max_words])
    return cut.rstrip(",;:") + "\u2026"
