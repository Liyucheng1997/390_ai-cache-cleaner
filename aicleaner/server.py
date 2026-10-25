"""本地 HTTP 服务：提供界面和 JSON 接口，只监听 127.0.0.1，并用随机令牌防止其他网页调用。"""
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import paths
from .cleaner import Cleaner
from .scanner import Scanner


def web_dir():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "web")


class App:
    def __init__(self):
        self.token = secrets.token_urlsafe(24)
        self.scanner = Scanner()
        self.cleaner = Cleaner()
        self.busy = threading.Lock()

    def start_scan(self, ids=None):
        if not self.busy.acquire(blocking=False):
            return False

        def job():
            try:
                self.scanner.scan(ids)
            finally:
                self.busy.release()
        threading.Thread(target=job, daemon=True).start()
        return True

    def start_clean(self, requests, mode):
        if not self.busy.acquire(blocking=False):
            return False

        def job():
            try:
                report = self.cleaner.run(requests, mode)
                self.scanner.scan([r["id"] for r in report])  # 清理后只重扫这些项
            finally:
                self.busy.release()
        threading.Thread(target=job, daemon=True).start()
        return True


def make_handler(app, port_ref):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AICleaner"

        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{port_ref[0]}", f"localhost:{port_ref[0]}")

        def _auth_ok(self):
            return secrets.compare_digest(self.headers.get("X-Token", ""), app.token)

        def _json(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                return {}
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return {}

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "forbidden"})
            route = self.path.split("?", 1)[0]
            if route in ("/", "/index.html"):
                with open(os.path.join(web_dir(), "index.html"), encoding="utf-8") as f:
                    html = f.read().replace("__TOKEN__", app.token)
                return self._send(200, html, "text/html; charset=utf-8")
            if route.startswith("/assets/"):
                name = route[len("/assets/"):]
                full = os.path.normpath(os.path.join(web_dir(), name))
                if not full.startswith(web_dir() + os.sep) or not os.path.isfile(full):
                    return self._send(404, {"error": "not found"})
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                with open(full, "rb") as f:
                    return self._send(200, f.read(), ctype)
            if not self._auth_ok():
                return self._send(401, {"error": "unauthorized"})
            if route == "/api/status":
                return self._send(200, {"scan": app.scanner.status(), "clean": app.cleaner.status(),
                                        "busy": app.busy.locked()})
            if route == "/api/result":
                return self._send(200, app.scanner.result or {})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok() or not self._auth_ok():
                return self._send(403, {"error": "forbidden"})
            route = self.path.split("?", 1)[0]
            data = self._json()
            if route == "/api/scan":
                return self._send(200, {"ok": app.start_scan()})
            if route == "/api/clean":
                items = [{"id": str(x.get("id")), "age": int(x.get("age") or 0)}
                         for x in data.get("items", []) if isinstance(x, dict)]
                mode = "delete" if data.get("mode") == "delete" else "recycle"
                return self._send(200, {"ok": app.start_clean(items, mode)})
            if route == "/api/reveal":
                ps = app.scanner.path_of(str(data.get("id")))
                idx = int(data.get("index") or 0)
                if 0 <= idx < len(ps) and os.path.lexists(ps[idx]) and os.name == "nt":
                    p = ps[idx]
                    args = ["explorer", p] if os.path.isdir(p) else ["explorer", "/select,", p]
                    subprocess.Popen(args)
                    return self._send(200, {"ok": True})
                return self._send(200, {"ok": False})
            return self._send(404, {"error": "not found"})

    return Handler


def serve(port=0):
    app = App()
    port_ref = [port]
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, port_ref))
    port_ref[0] = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return app, httpd, f"http://127.0.0.1:{port_ref[0]}/"


__all__ = ["serve", "App", "paths"]
