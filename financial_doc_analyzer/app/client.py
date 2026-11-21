"""Thin HTTP gateway client. Swapping mock -> real gateway = change MOCK_BASE_URL (+ GATEWAY_API_KEY)."""
import http.client
import json as _json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional
from . import config


class UpstreamError(RuntimeError):
    """The retrieval gateway is unreachable or returned a 5xx."""


class NotFound(LookupError):
    """The gateway answered 404 for this resource."""


_http = None


class _Resp:
    def __init__(self, status: int, body: bytes):
        self.status_code = status
        self.text = body.decode("utf-8", "replace")

    def json(self):
        return _json.loads(self.text)


class UrllibSession:
    """Minimal requests-like HTTP client on the standard library.

    Deliberately avoids the ``requests`` package: importing it builds an SSL context, which can hang for minutes on
    some Windows setups (Microsoft Store Python + antivirus). Plain ``http://`` calls (the mock gateway on localhost)
    use ``http.client`` directly, so no SSL context is ever created. ``https://`` gateways go through urllib, where
    the SSL context is created only because it is really needed.
    """

    def _do(self, method, url, params=None, json=None, headers=None, timeout=10):
        if params:
            q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url += ("&" if "?" in url else "?") + q
        h = dict(headers or {})
        data = None
        if json is not None:
            data = _json.dumps(json).encode("utf-8")
            h["Content-Type"] = "application/json"
        u = urllib.parse.urlparse(url)
        if u.scheme == "http":
            # http.client sends the path verbatim, so encode spaces etc. ("Risk Factors") like `requests` did
            path = urllib.parse.quote(u.path or "/", safe="/%:@&=+$,;-._~!*'()") + (("?" + u.query) if u.query else "")
            host = "127.0.0.1" if u.hostname == "localhost" else u.hostname   # avoid the IPv6-first delay on Windows
            conn = http.client.HTTPConnection(host, u.port or 80, timeout=timeout)
            try:
                conn.request(method, path, body=data, headers=h)
                r = conn.getresponse()
                return _Resp(r.status, r.read())
            finally:
                conn.close()
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return _Resp(r.status, r.read())
        except urllib.error.HTTPError as e:      # 4xx/5xx are responses, not exceptions
            return _Resp(e.code, e.read())

    def get(self, url, params=None, headers=None, timeout=10):
        return self._do("GET", url, params=params, headers=headers, timeout=timeout)

    def post(self, url, json=None, params=None, headers=None, timeout=10):
        return self._do("POST", url, params=params, json=json, headers=headers, timeout=timeout)


def set_http(obj) -> None:
    """Inject an object with .get/.post (requests.Session-like). Used by tests and in-process evals."""
    global _http
    _http = obj


def _session():
    global _http
    if _http is None:
        _http = UrllibSession()
    return _http


def _headers() -> Dict[str, str]:
    h = {"Accept": "application/json", "User-Agent": "financial-doc-analyzer/0.2"}
    if config.api_key():
        h["Authorization"] = f"Bearer {config.api_key()}"
    return h


def request(method: str, path: str, *, params=None, json=None, retries: int = 1) -> Any:
    url = f"{config.base_url()}{path}"
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            if method == "GET":
                r = _session().get(url, params=params, headers=_headers(), timeout=config.http_timeout())
            else:
                r = _session().post(url, json=json, headers=_headers(), timeout=config.http_timeout())
        except Exception as e:  # connection errors, timeouts
            last = e
            time.sleep(0.2 * (attempt + 1))
            continue
        if r.status_code == 404:
            raise NotFound(path)
        if r.status_code >= 500:
            last = UpstreamError(f"{path} -> HTTP {r.status_code}")
            time.sleep(0.2 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise UpstreamError(f"{path} -> HTTP {r.status_code}: {r.text[:200]}")
        return r.json()
    raise UpstreamError(f"gateway unreachable at {url}: {last}")
