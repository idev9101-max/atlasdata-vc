# AtlasData mirror — thin domain front for the zrok backend.
# Proxies every request upstream; on a 402 it rewrites resource.url to this
# host so buyers pay against the Render domain, keeping the backend's tuned
# accept rails, timeouts, extras and bazaar metadata.
import json, base64, os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

UPSTREAM = "https://x402atlas.xyz"
UP_ORIGIN = urlparse(UPSTREAM).netloc

INDEX = {
    "service": "AtlasData",
    "docs": "https://atlasdata.onrender.com/.well-known/x402",
    "endpoints": "see upstream catalog",
}


def _public_origin(headers):
    host = headers.get("x-forwarded-host") or headers.get("host") or "atlasdata.onrender.com"
    proto = headers.get("x-forwarded-proto") or "https"
    return f"{proto}://{host}"


HOSTS = ["atlasdata.shares.zrok.io", "xz4yh0o10qy2.shares.zrok.io",
         "r4h1wrm8bt8l.shares.zrok.io"]


def _rewrite_resource_url(header_value, origin):
    try:
        ch = json.loads(base64.b64decode(header_value).decode())
        host = urlparse(origin).netloc
        raw = json.dumps(ch)
        for h in HOSTS:
            raw = raw.replace("https://" + h, origin).replace(h, host)
        ch = json.loads(raw)
        return base64.b64encode(json.dumps(ch, separators=(",", ":")).encode()).decode()
    except Exception:
        return header_value


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body=b"", ctype="application/json", extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, method):
        u = urlparse(self.path)
        target = UPSTREAM + u.path + (("?" + u.query) if u.query else "")
        body = None
        if method in ("POST", "PUT", "PATCH"):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n) if n else b"{}"
        headers = {"user-agent": "atlasdata-mirror/1.0"}
        for h in ("payment-signature", "content-type", "x-payment"):
            v = self.headers.get(h)
            if v:
                headers[h] = v
        req = urllib.request.Request(target, data=body, headers=headers, method=method)
        try:
            r = urllib.request.urlopen(req, timeout=60)
            resp_body, status, rheaders = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            resp_body, status, rheaders = e.read(), e.code, (e.headers or {})
        except Exception:
            return self._send(502, json.dumps({"error": "upstream unreachable"}))
        extra = {}
        pr = rheaders.get("payment-response") if rheaders else None
        if pr:
            extra["payment-response"] = pr
        req_h = rheaders.get("payment-required") if rheaders else None
        if status == 402 and req_h:
            extra["payment-required"] = _rewrite_resource_url(req_h, _public_origin(self.headers))
        return self._send(status, resp_body,
                          (rheaders.get("content-type") if rheaders else None) or "application/json",
                          extra)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/healthz"):
            return self._send(200, json.dumps(INDEX))
        if u.path in ("/.well-known/x402", "/llms.txt", "/payapi-verify.txt",
                      "/.well-known/payapi-verify.txt"):
            return self._proxy("GET")
        return self._proxy("GET")

    def do_POST(self):
        return self._proxy("POST")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("content-length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


PORT = int(os.environ.get("PORT", "7860"))
ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
