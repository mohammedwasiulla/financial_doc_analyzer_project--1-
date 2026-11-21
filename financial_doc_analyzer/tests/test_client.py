import json, ssl, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs
import pytest
from app.client import UrllibSession


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _reply(self, body=None):
        u = urlparse(self.path)
        payload = {"path": unquote(u.path), "query": parse_qs(u.query), "body": body}
        data = json.dumps(payload).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        if "missing" in self.path:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        self._reply()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self._reply(json.loads(self.rfile.read(n) or b"null"))


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_paths_with_spaces_and_ampersand_are_encoded(server):
    r = UrllibSession().get(f"{server}/doc/ACMR_2023/section/Risk Factors")
    assert r.status_code == 200 and r.json()["path"] == "/doc/ACMR_2023/section/Risk Factors"
    assert UrllibSession().get(f"{server}/doc/X/section/MD&A").json()["path"] == "/doc/X/section/MD&A"


def test_query_params_json_body_and_404(server):
    s = UrllibSession()
    assert s.get(f"{server}/search", params={"q": "a b", "top_k": 5, "filing_id": None}).json()["query"] == {"q": ["a b"], "top_k": ["5"]}
    assert s.post(f"{server}/x", json={"k": 1}).json()["body"] == {"k": 1}
    assert s.get(f"{server}/missing").status_code == 404


def test_plain_http_never_creates_an_ssl_context(server, monkeypatch):
    """Regression for the Windows hang: SSLContext creation is what froze `import requests`."""
    def boom(cls, *a, **k):
        raise RuntimeError("SSL context created")
    monkeypatch.setattr(ssl.SSLContext, "__new__", boom)
    assert UrllibSession().get(f"{server}/ok").status_code == 200


def test_localhost_is_connected_as_127_0_0_1(server, monkeypatch):
    """Windows resolves 'localhost' to IPv6 first (about 2 s penalty per new connection)."""
    import http.client
    seen = []
    real = http.client.HTTPConnection

    class Spy(real):
        def __init__(self, host, *a, **k):
            seen.append(host)
            super().__init__(host, *a, **k)
    monkeypatch.setattr(http.client, "HTTPConnection", Spy)
    port = server.rsplit(":", 1)[1]
    assert UrllibSession().get(f"http://localhost:{port}/ok").status_code == 200
    assert seen == ["127.0.0.1"]
