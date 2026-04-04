"""
proxy.py — Single-port reverse proxy
Routes /auth/* and /users* → FastAPI auth service (port 5001)
Routes everything else      → Flask API (port 5000)
Listens on port 8080
"""
import threading
import re
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

_LOCALHOST_RE = re.compile(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$')
_RAW = os.environ.get('ALLOWED_ORIGINS', '')
_ALLOWED = {o.strip() for o in _RAW.split(',') if o.strip()}

def _cors_origin(handler) -> str:
    origin = handler.headers.get('Origin', '')
    if origin and (_LOCALHOST_RE.match(origin) or origin in _ALLOWED):
        return origin
    return ''

FLASK_URL   = "http://127.0.0.1:5000"
FASTAPI_URL = "http://127.0.0.1:5001"

AUTH_PREFIXES = ("/auth/", "/users", "/auth")

def target(path):
    return FASTAPI_URL if (path.startswith(AUTH_PREFIXES) or path == "/users") else FLASK_URL

class Proxy(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence per-request logs

    def _proxy(self):
        dest = target(self.path) + self.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None

        # Forward all headers except Host
        fwd_headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in ("host", "content-length")}
        if body:
            fwd_headers["Content-Length"] = str(len(body))

        req = urllib.request.Request(dest, data=body, headers=fwd_headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ("content-type", "content-length", "set-cookie", "authorization"):
                        self.send_header(k, v)
                _co = _cors_origin(self)
                if _co:
                    self.send_header("Access-Control-Allow-Origin", _co)
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH")
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            _co = _cors_origin(self)
            if _co:
                self.send_header("Access-Control-Allow-Origin", _co)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            _co = _cors_origin(self)
            if _co:
                self.send_header("Access-Control-Allow-Origin", _co)
            self.end_headers()
            self.wfile.write(f'{{"error":"proxy error: {e}"}}'.encode())

    def do_OPTIONS(self):
        self.send_response(200)
        _co = _cors_origin(self)
        if _co:
            self.send_header("Access-Control-Allow-Origin", _co)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH")
        self.end_headers()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _proxy


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Proxy)
    print("Proxy running on http://0.0.0.0:8080")
    print(f"  /auth/* and /users* -> {FASTAPI_URL}")
    print(f"  everything else     -> {FLASK_URL}")
    server.serve_forever()
