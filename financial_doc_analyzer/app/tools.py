from functools import lru_cache
from typing import Any, Dict
from . import client


def risk_score(text: str) -> Dict[str, Any]:
    return client.request("POST", "/tools/risk/score", json={"text": text})


@lru_cache(maxsize=2048)
def cached_risk_score(text: str) -> float:
    return float(risk_score(text).get("score", 0.0))
