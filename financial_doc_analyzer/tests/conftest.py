import os, sys, warnings
import pytest
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from app.asgi_client import ASGIClient as TestClient  # noqa: E402

BASE = "http://127.0.0.1:8030"
os.environ["MOCK_BASE_URL"] = BASE


class Adapter:
    """requests-like facade over the in-memory mock; ``mutate`` lets tests degrade the gateway."""
    def __init__(self, tc, mutate=None, fail=False):
        self.tc, self.mutate, self.fail = tc, mutate, fail

    def _go(self, method, url, **kw):
        if self.fail:
            raise ConnectionError("gateway down")
        path = url[len(BASE):]
        r = getattr(self.tc, method)(path, **kw)
        return self.mutate(path, r) if self.mutate else r

    def get(self, url, params=None, headers=None, timeout=None):
        return self._go("get", url, params=params)

    def post(self, url, json=None, headers=None, timeout=None):
        return self._go("post", url, json=json)


@pytest.fixture
def make_api():
    from mock_server.main import app as mock_app
    from app.server import app as app_app
    from app import client, retrieval, tools
    mock = TestClient(mock_app)

    def _make(mutate=None, fail=False):
        client.set_http(Adapter(mock, mutate, fail))
        retrieval.clear_caches()
        tools.cached_risk_score.cache_clear()
        return TestClient(app_app)
    yield _make
    client.set_http(None)


@pytest.fixture
def api(make_api):
    return make_api()
