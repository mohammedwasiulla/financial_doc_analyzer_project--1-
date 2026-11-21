import logging, time
from typing import List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import client, retrieval
from .analyzer import FilingNotFound, answer_question, retrieve, summarize_risks
from .models import QAReq, QAResp, RetrieveHit, RiskReq, RiskResp

log = logging.getLogger("fda")
app = FastAPI(
    title="Financial Document Analyzer",
    version="0.2.0",
    description="Clause-level Q&A (/qa) and risk summaries (/risksummary) over 10-K-style filings, "
                "served by a retrieval gateway (mock by default).",
)


@app.exception_handler(client.UpstreamError)
async def _upstream(_: Request, exc: client.UpstreamError):
    return JSONResponse(status_code=503, content={"detail": f"retrieval gateway unavailable: {exc}"})


@app.middleware("http")
async def _timing(request: Request, call_next):
    t = time.perf_counter()
    resp = await call_next(request)
    log.info("%s %s -> %s in %.0f ms", request.method, request.url.path, resp.status_code, (time.perf_counter() - t) * 1000)
    return resp


@app.get("/health")
def health():
    try:
        n = len(retrieval.list_filings(ttl=0))
        return {"status": "ok", "gateway": "reachable", "filings": n}
    except client.UpstreamError as e:
        return JSONResponse(status_code=503, content={"status": "degraded", "gateway": str(e)})


@app.post("/qa", response_model=QAResp)
def qa(req: QAReq):
    return answer_question(req.question, req.filing_id)


@app.post("/risksummary", response_model=RiskResp)
def risksummary(req: RiskReq):
    try:
        return summarize_risks(req.filing_id, req.max_bullets)
    except FilingNotFound:
        raise HTTPException(404, f"Filing {req.filing_id} not found in the corpus.")


@app.post("/debug/retrieve", response_model=List[RetrieveHit], tags=["diagnostics"])
def debug_retrieve(req: QAReq, top_k: int = 5):
    """Ranked (filing, section) list behind /qa. Used by scripts/eval_retrieval.py."""
    return retrieve(req.question, req.filing_id, top_k=top_k)
