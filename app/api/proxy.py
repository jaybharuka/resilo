"""
proxy.py - Single-port reverse proxy
Routes all traffic -> FastAPI service (port 5001)
Listens on port 8080
"""
<<<<<<< HEAD
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
=======
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
>>>>>>> ed21fa0 (Phase 2 complete: realtime, AI resilience, full test isolation with Postgres)
import urllib.error
import urllib.request

_LOCALHOST_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")
_RAW = os.environ.get("ALLOWED_ORIGINS", "")
_ALLOWED = {o.strip() for o in _RAW.split(",") if o.strip()}

<<<<<<< HEAD
FLASK_URL   = "http://127.0.0.1:5000"
=======

def _cors_origin(handler) -> str:
    origin = handler.headers.get("Origin", "")
    if origin and (_LOCALHOST_RE.match(origin) or origin in _ALLOWED):
        return origin
    return ""


>>>>>>> ed21fa0 (Phase 2 complete: realtime, AI resilience, full test isolation with Postgres)
FASTAPI_URL = "http://127.0.0.1:5001"


def target(path: str) -> str:
    return FASTAPI_URL


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _proxy(self):
        dest = target(self.path) + self.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None

        fwd_headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "content-length")
        }
        if body:
            fwd_headers["Content-Length"] = str(len(body))

        req = urllib.request.Request(dest, data=body, headers=fwd_headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ("content-type", "content-length", "set-cookie", "authorization"):
                        self.send_header(k, v)
<<<<<<< HEAD
                # Always allow CORS from Firebase
                self.send_header("Access-Control-Allow-Origin", "*")
=======
                _co = _cors_origin(self)
                if _co:
                    self.send_header("Access-Control-Allow-Origin", _co)
                    self.send_header("Vary", "Origin")
>>>>>>> ed21fa0 (Phase 2 complete: realtime, AI resilience, full test isolation with Postgres)
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH")
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
<<<<<<< HEAD
            self.send_header("Access-Control-Allow-Origin", "*")
=======
            _co = _cors_origin(self)
            if _co:
                self.send_header("Access-Control-Allow-Origin", _co)
                self.send_header("Vary", "Origin")
>>>>>>> ed21fa0 (Phase 2 complete: realtime, AI resilience, full test isolation with Postgres)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            print(f"Proxy upstream error: {e}")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
<<<<<<< HEAD
            self.send_header("Access-Control-Allow-Origin", "*")
=======
            _co = _cors_origin(self)
            if _co:
                self.send_header("Access-Control-Allow-Origin", _co)
                self.send_header("Vary", "Origin")
>>>>>>> ed21fa0 (Phase 2 complete: realtime, AI resilience, full test isolation with Postgres)
            self.end_headers()
            self.wfile.write(b'{"error":"upstream unavailable"}')

    def do_OPTIONS(self):
        self.send_response(200)
<<<<<<< HEAD
        self.send_header("Access-Control-Allow-Origin", "*")
=======
        _co = _cors_origin(self)
        if _co:
            self.send_header("Access-Control-Allow-Origin", _co)
            self.send_header("Vary", "Origin")
>>>>>>> ed21fa0 (Phase 2 complete: realtime, AI resilience, full test isolation with Postgres)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH")
        self.end_headers()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _proxy


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Proxy)
    print("Proxy running on http://0.0.0.0:8080")
    print(f"  all routes -> {FASTAPI_URL}")
    server.serve_forever()
