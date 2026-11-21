
from typing import Dict, Any, List, Optional
from . import retrieval, tools

def best_snippet_for_query(question: str, filing_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    res = retrieval.search(q=question, filing_id=filing_id, top_k=5)
    results = res.get("results", [])
    return results[0] if results else None

def answer_question(question: str, filing_id: Optional[str] = None) -> Dict[str, Any]:
    hit = best_snippet_for_query(question, filing_id)
    if not hit:
        return {"answer": "I don't know.", "citations": []}
    snippet = hit["snippet"]
    sec = hit["section"]
    fid = hit["filing_id"]
    answer = snippet.split(".")[0].strip() + "."
    return {"answer": answer, "citations": [{"filing_id": fid, "section": sec}]}

def summarize_risks(filing_id: str, max_bullets: int = 4) -> Dict[str, Any]:
    # Bias toward the Risk Factors section if we can retrieve it
    res = retrieval.search(q="risk compliance breach regulatory supply volatility privacy penalties", filing_id=filing_id, top_k=5)
    bullets: List[str] = []
    cites: List[Dict[str, str]] = []
    for r in res.get("results", []):
        if len(bullets) >= max_bullets:
            break
        text = r["snippet"]
        score = tools.risk_score(text).get("score", 0.0)
        if score > 0:  # keep simple
            sent = text.split(".")[0].strip()
            if sent and sent not in bullets:
                bullets.append(sent if len(sent) < 140 else sent[:137] + "...")
                cites.append({"filing_id": r["filing_id"], "section": r["section"]})
    if not bullets:
        bullets = ["No high-signal risk sentences found."]
    return {"summary": bullets, "citations": cites}
