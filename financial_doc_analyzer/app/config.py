"""Runtime configuration (read at call time so tests / the CLI can override env vars)."""
import os


def base_url() -> str:
    return os.getenv("MOCK_BASE_URL", "http://127.0.0.1:8030").rstrip("/")


def api_key():
    return os.getenv("GATEWAY_API_KEY") or None


def http_timeout() -> float:
    return float(os.getenv("HTTP_TIMEOUT", "10"))


def qa_min_confidence() -> float:
    return float(os.getenv("QA_MIN_CONFIDENCE", "0.55"))


def risk_bullets() -> int:
    return max(3, min(5, int(os.getenv("RISK_BULLETS", "4"))))
