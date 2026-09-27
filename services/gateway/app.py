import os
import urllib.error
from pathlib import Path

from common.http import Handler, read_json, request, respond, serve, log

REQUESTS = os.getenv("REQUESTS_URL", "http://localhost:8102")
API_KEY = os.getenv("API_KEY", "development-key")
DEV_MODE = os.getenv("DEV_MODE") == "1"
WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


class API(Handler):
    def auth(self):
        if self.headers.get("X-API-Key") != API_KEY:
            respond(self, 401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        if self.path == "/health":
            return respond(self, 200, {"status": "ok"})
        if DEV_MODE and self.path == "/dev-config":
            return respond(self, 200, {"api_key": API_KEY})
        if self.path in ("/", "/style.css", "/app.js"):
            name = "index.html" if self.path == "/" else self.path[1:]
            content_type = {"index.html": "text/html; charset=utf-8", "style.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}[name]
            data = (WEB_ROOT / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(data)
        if not self.auth():
            return
        if not self.path.startswith("/requests/") or "/" in self.path[len("/requests/"):]:
            return respond(self, 404, {"error": "not_found"})
        try:
            status, data = request("GET", REQUESTS + self.path)
            respond(self, status, data)
        except (OSError, urllib.error.URLError):
            respond(self, 503, {"error": "request_service_unavailable"})

    def do_POST(self):
        if not self.auth():
            return
        if self.path != "/requests":
            return respond(self, 404, {"error": "not_found"})
        try:
            body = read_json(self)
            cid = self.headers.get("X-Correlation-ID", "")
            status, data = request("POST", REQUESTS + "/requests", body, {"X-Correlation-ID": cid})
            log("gateway", "create_forwarded", data.get("correlation_id", cid), status=status)
            respond(self, status, data)
        except ValueError as exc:
            respond(self, 400, {"error": str(exc)})
        except (OSError, urllib.error.URLError):
            respond(self, 503, {"error": "request_service_unavailable"})


if __name__ == "__main__":
    serve(API, 8100)
