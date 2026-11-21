"""Mock Financial Filings API (synthetic corpus).

Original kit endpoints are unchanged in behaviour:
  GET  /search, GET /doc/{filing_id}, GET /tools/section/list, POST /tools/risk/score

Additive changes (schema-compatible; existing clients keep working):
  * /search results carry an extra ``text`` field with the full section text
    (``snippet`` is still the first 220 chars, as in the original kit).
  * GET /doc/{filing_id}/section/{section}   -> full text of one section
  * GET /filings                             -> list of available filing ids
  * GET /health
  * CORPUS_DIR env var (needed for Docker) and filing-id validation
    (the original joined the raw id into a path -> path traversal).
"""
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
import os, re, glob

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
CORPUS_DIR = os.getenv("CORPUS_DIR") or os.path.join(os.path.dirname(APP_ROOT), "corpus", "filings")

SECTION_NAMES = ["Business", "Risk Factors", "MD&A", "Legal Proceedings", "Financials"]
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

app = FastAPI(title="Mock Financial Filings API", version="0.2.0")


def load_filing_text(filing_id: str) -> Optional[str]:
    if not _ID_RE.match(filing_id):
        return None
    path = os.path.join(CORPUS_DIR, f"{filing_id}.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def split_sections(md_text: str) -> Dict[str, str]:
    sections: Dict[str, list] = {}
    current = None
    for ln in md_text.splitlines():
        if ln.startswith("## "):
            current = ln.replace("## ", "").strip()
            sections[current] = []
        elif current:
            sections[current].append(ln)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


@app.get("/health")
def health():
    return {"status": "ok", "filings": len(glob.glob(os.path.join(CORPUS_DIR, "*.md")))}


@app.get("/tools/section/list")
def section_list():
    return {"sections": SECTION_NAMES}


class RiskReq(BaseModel):
    text: str


RISK_KEYWORDS = ["risk", "breach", "cyber", "regulatory", "compliance", "litigation",
                 "supply", "volatility", "privacy", "penalties"]


@app.post("/tools/risk/score")
def risk_score(req: RiskReq):
    text = req.text.lower()
    score = sum(text.count(k) for k in RISK_KEYWORDS) / max(1, len(text.split()))
    return {"score": score}


@app.get("/filings")
def list_filings():
    ids = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(CORPUS_DIR, "*.md")))
    return {"filings": ids}


@app.get("/doc/{filing_id}")
def get_doc(filing_id: str):
    md = load_filing_text(filing_id)
    if not md:
        return {"filing_id": filing_id, "exists": False}
    secs = split_sections(md)
    return {"filing_id": filing_id, "exists": True, "sections": list(secs.keys()),
            "title": f"{filing_id} Annual Filing"}


@app.get("/doc/{filing_id}/section/{section:path}")
def get_section(filing_id: str, section: str):
    md = load_filing_text(filing_id)
    if not md:
        raise HTTPException(404, f"unknown filing {filing_id}")
    secs = split_sections(md)
    if section not in secs:
        raise HTTPException(404, f"unknown section {section}")
    return {"filing_id": filing_id, "section": section, "text": secs[section]}


@app.get("/search")
def search(q: str = Query(...), filing_id: Optional[str] = None, top_k: int = Query(5, ge=1, le=100)):
    results = []
    files = [os.path.basename(p).replace(".md", "") for p in glob.glob(os.path.join(CORPUS_DIR, "*.md"))]
    for fid in files:
        if filing_id and fid != filing_id:
            continue
        md = load_filing_text(fid)
        if not md:
            continue
        for sec_name, sec_text in split_sections(md).items():
            text_lower = sec_text.lower()
            score = sum(text_lower.count(tok) for tok in q.lower().split())
            if score > 0:
                snippet = sec_text[:220].replace("\n", " ")
                results.append({"filing_id": fid, "section": sec_name, "score": float(score),
                                "snippet": snippet, "text": sec_text})
    results = sorted(results, key=lambda x: (-x["score"], x["filing_id"], x["section"]))[:top_k]
    return {"query": q, "results": results}
