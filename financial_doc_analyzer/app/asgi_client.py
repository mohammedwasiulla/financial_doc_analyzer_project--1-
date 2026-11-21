"""Tiny in-memory client for ASGI apps (FastAPI) - a stand-in for fastapi.testclient.TestClient.

TestClient is built on httpx, which creates an SSL context when instantiated; that can hang on some Windows
setups. This calls the ASGI app directly: no sockets, no httpx, no SSL.
"""
import asyncio
import json as _json
import urllib.parse


class Response:
    def __init__(self, status: int, body: bytes):
        self.status_code = status
        self.content = body
        self.text = body.decode("utf-8", "replace")

    def json(self):
        return _json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text[:200]}")


class ASGIClient:
    def __init__(self, app):
        self.app = app

    def _call(self, method: str, path: str, params=None, json=None) -> Response:
        path, _, qs = path.partition("?")
        q = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        qs = "&".join(x for x in (qs, q) if x)
        body = _json.dumps(json).encode("utf-8") if json is not None else b""
        headers = [(b"host", b"testserver")]
        if json is not None:
            headers += [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
                 "path": urllib.parse.unquote(path), "raw_path": urllib.parse.quote(path).encode(),
                 "query_string": qs.encode(), "headers": headers, "client": ("127.0.0.1", 50000),
                 "server": ("testserver", 80), "root_path": ""}

        async def run() -> Response:
            done, sent_body = asyncio.Event(), False
            out = {"status": 500, "body": b""}

            async def receive():
                nonlocal sent_body
                if not sent_body:
                    sent_body = True
                    return {"type": "http.request", "body": body, "more_body": False}
                await done.wait()
                return {"type": "http.disconnect"}

            async def send(msg):
                if msg["type"] == "http.response.start":
                    out["status"] = msg["status"]
                elif msg["type"] == "http.response.body":
                    out["body"] += msg.get("body", b"")
                    if not msg.get("more_body", False):
                        done.set()

            await self.app(scope, receive, send)
            return Response(out["status"], out["body"])

        return asyncio.run(run())

    def get(self, path, params=None, **_):
        return self._call("GET", path, params=params)

    def post(self, path, json=None, params=None, **_):
        return self._call("POST", path, params=params, json=json)
