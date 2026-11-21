"""Shared helpers for the evaluation scripts.

Two modes:
  * HTTP (default)  : talks to the running servers (APP_BASE_URL / MOCK_BASE_URL)
  * --inprocess     : spins both FastAPI apps up in memory (no ports needed; used by CI and run_all_evals)
"""
import csv, json, os, sys, warnings
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

APP_BASE = os.getenv("APP_BASE_URL", "http://127.0.0.1:9025")
MOCK_BASE = os.getenv("MOCK_BASE_URL", "http://127.0.0.1:8030")


class _Adapter:
    """requests-like facade over a Starlette TestClient (so app.client can call the mock in-process)."""
    def __init__(self, tc, base):
        self.tc, self.base = tc, base.rstrip("/")

    def _p(self, url):
        return url[len(self.base):] if url.startswith(self.base) else url

    def get(self, url, params=None, headers=None, timeout=None):
        return self.tc.get(self._p(url), params=params)

    def post(self, url, json=None, headers=None, timeout=None):
        return self.tc.post(self._p(url), json=json)


class Api:
    def __init__(self, inprocess: bool = False):
        self.inprocess = inprocess
        if inprocess:
            from app.asgi_client import ASGIClient as TestClient
            from mock_server.main import app as mock_app
            from app.server import app as app_app
            from app import client, retrieval
            os.environ["MOCK_BASE_URL"] = MOCK_BASE
            self._mock = TestClient(mock_app)
            self._app = TestClient(app_app)
            client.set_http(_Adapter(self._mock, MOCK_BASE))
            retrieval.clear_caches()
        else:
            from app.client import UrllibSession
            self._s = UrllibSession()

    def app_post(self, path: str, json: Dict[str, Any], **params) -> Dict[str, Any]:
        if self.inprocess:
            return self._app.post(path, json=json, params=params or None).json()
        try:
            return self._s.post(f"{APP_BASE}{path}", json=json, params=params or None, timeout=120).json()
        except OSError as e:
            raise SystemExit(f"Cannot reach the app at {APP_BASE} ({e}).\nStart both servers first (see README), or add --inprocess.")

    def mock_get(self, path: str, **params) -> Dict[str, Any]:
        if self.inprocess:
            return self._mock.get(path, params=params).json()
        try:
            return self._s.get(f"{MOCK_BASE}{path}", params=params, timeout=120).json()
        except OSError as e:
            raise SystemExit(f"Cannot reach the mock server at {MOCK_BASE} ({e}).\nStart both servers first (see README), or add --inprocess.")


def load_eval(path: Optional[str] = None) -> List[Dict[str, str]]:
    with open(path or os.path.join(ROOT, "evaluation", "eval_qna.csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_gold() -> Dict[str, List[str]]:
    return json.load(open(os.path.join(ROOT, "evaluation", "gold_risk_topics.json"), encoding="utf-8"))


def results_dir() -> str:
    d = os.path.join(ROOT, "evaluation", "results")
    os.makedirs(d, exist_ok=True)
    return d


def add_common_args(ap):
    ap.add_argument("--inprocess", action="store_true", help="run both apps in memory (no servers needed)")
    ap.add_argument("--json", action="store_true", help="print metrics as JSON")
    return ap
