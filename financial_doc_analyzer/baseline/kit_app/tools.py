
import os, requests
from typing import Dict, Any

MOCK_BASE_URL = os.getenv("MOCK_BASE_URL", "http://localhost:8030")

def risk_score(text: str) -> Dict[str, Any]:
    r = requests.post(f"{MOCK_BASE_URL}/tools/risk/score", json={"text": text}, timeout=10)
    r.raise_for_status()
    return r.json()
