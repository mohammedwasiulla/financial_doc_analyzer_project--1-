"""Retrieval layer on top of the gateway's /search (plus /doc fallbacks)."""
import time
from typing import Any, Dict, List, Optional
from . import client

_FILINGS_CACHE: Dict[str, Any] = {"t": 0.0, "ids": []}
_DOC_CACHE: Dict[str, Optional[Dict[str, str]]] = {}


def clear_caches() -> None:
    _FILINGS_CACHE.update(t=0.0, ids=[])
    _DOC_CACHE.clear()


def search(q: str, filing_id: Optional[str] = None, top_k: int = 5) -> Dict[str, Any]:
    params: Dict[str, Any] = {"q": q, "top_k": top_k}
    if filing_id:
        params["filing_id"] = filing_id
    return client.request("GET", "/search", params=params)


def get_doc(filing_id: str) -> Dict[str, Any]:
    return client.request("GET", f"/doc/{filing_id}")


def section_list() -> Dict[str, Any]:
    return client.request("GET", "/tools/section/list")


def get_section(filing_id: str, section: str) -> Optional[str]:
    try:
        return client.request("GET", f"/doc/{filing_id}/section/{section}").get("text")
    except client.NotFound:
        return None


def list_filings(ttl: float = 300.0) -> List[str]:
    """Known filing ids. Tries GET /filings; falls back to a broad /search if the gateway lacks it."""
    if _FILINGS_CACHE["ids"] and time.time() - _FILINGS_CACHE["t"] < ttl:
        return _FILINGS_CACHE["ids"]
    try:
        ids = sorted(client.request("GET", "/filings").get("filings", []))
    except client.NotFound:
        res = search("risk revenue operates litigation management", top_k=100).get("results", [])
        ids = sorted({r["filing_id"] for r in res})
    _FILINGS_CACHE.update(t=time.time(), ids=ids)
    return ids


def hit_text(hit: Dict[str, Any]) -> str:
    """Full section text. Uses ``text`` if the gateway sends it, else /doc/.../section, else the snippet."""
    if hit.get("text"):
        return hit["text"]
    full = get_section(hit["filing_id"], hit["section"])
    return full or hit.get("snippet", "")


def load_filing(filing_id: str) -> Optional[Dict[str, str]]:
    """section name -> text, or None if the filing does not exist."""
    if filing_id in _DOC_CACHE:
        return _DOC_CACHE[filing_id]
    doc = get_doc(filing_id)
    if not doc.get("exists", True):
        _DOC_CACHE[filing_id] = None
        return None
    secs: Dict[str, str] = {}
    for name in doc.get("sections", []):
        txt = get_section(filing_id, name)
        if txt is not None:
            secs[name] = txt
    if not secs:  # gateway has no section endpoint: rebuild from a broad search
        res = search("risk revenue operates litigation management compliance", filing_id=filing_id, top_k=20)
        for r in res.get("results", []):
            secs[r["section"]] = hit_text(r)
    _DOC_CACHE[filing_id] = secs
    return secs
