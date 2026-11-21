
import os, requests
from typing import Dict, Any, Optional

MOCK_BASE_URL = os.getenv("MOCK_BASE_URL", "http://localhost:8030")

def search(q: str, filing_id: Optional[str] = None, top_k: int = 5) -> Dict[str, Any]:
    params = {"q": q, "top_k": top_k}
    if filing_id:
        params["filing_id"] = filing_id
    r = requests.get(f"{MOCK_BASE_URL}/search", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def get_doc(filing_id: str) -> Dict[str, Any]:
    r = requests.get(f"{MOCK_BASE_URL}/doc/{filing_id}", timeout=10)
    r.raise_for_status()
    return r.json()

def section_list() -> Dict[str, Any]:
    r = requests.get(f"{MOCK_BASE_URL}/tools/section/list", timeout=10)
    r.raise_for_status()
    return r.json()
