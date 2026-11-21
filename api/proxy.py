# Vercel serverless catch-all: proxy to zrok backend, rewrite 402 host.
import json, base64, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

UPSTREAM = "https://x402atlas.xyz"
HOSTS = ["x402atlas.xyz", "atlasdata.onrender.com",
         "atlasdata.shares.zrok.io", "xz4yh0o10qy2.shares.zrok.io",
         "r4h1wrm8bt8l.shares.zrok.io"]


def _rewrite(header_value, origin):
    try:
        ch = json.loads(base64.b64decode(header_value).decode())
        raw = json.dumps(ch)
        host = urlparse(origin).netloc
        for h in HOSTS:
            raw = raw.replace("https://" + h, origin).replace(h, host)
        return base64.b64encode(json.dumps(json.loads(raw), separators=(",", ":")).encode()).decode()
    except Exception:
        return header_value


class handler(BaseHTTPRequestHandler):
    def _origin(self):
        host = self.headers.get("x-forwarded-host") or self.headers.get("host")
        return "https://" + host

    def _run(self, method):
        u = urlparse(self.path)
        body = None
        if method in ("POST", "PUT", "PATCH"):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n) if n else b"{}"
        h = {"user-agent": "atlasdata-mirror/1.0"}
        for k in ("payment-signature", "content-type", "x-payment"):
            v = self.headers.get(k)
            if v:
                h[k] = v
        req = urllib.request.Request(UPSTREAM + u.path + (("?" + u.query) if u.query else ""),
                                     data=body, headers=h, method=method)
        try:
            r = urllib.request.urlopen(req, timeout=55)
            status, rbody, rh = r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            status, rbody, rh = e.code, e.read(), (e.headers or {})
        except Exception:
            status, rbody, rh = 502, json.dumps({"error": "upstream unreachable"}).encode(), {}
        self.send_response(status)
        self.send_header("content-type", (rh.get("content-type") if rh else None) or "application/json")
        if rh:
            pr = rh.get("payment-response")
            if pr:
                self.send_header("payment-response", pr)
            rq = rh.get("payment-required")
            if status == 402 and rq:
                self.send_header("payment-required", _rewrite(rq, self._origin()))
        self.send_header("content-length", str(len(rbody)))
        self.end_headers()
        self.wfile.write(rbody)

    def do_GET(self):
        self._run("GET")

    def do_POST(self):
        self._run("POST")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("content-length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass
