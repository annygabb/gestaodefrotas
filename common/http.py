import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def database(name):
    os.makedirs(os.getenv("DATA_DIR", "./data"), exist_ok=True)
    db = sqlite3.connect(os.path.join(os.getenv("DATA_DIR", "./data"), name), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=15000")
    return db


def request(method, url, payload=None, headers=None, timeout=3):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except (ValueError, OSError):
            return exc.code, {"error": "upstream_error"}


def respond(handler, status, body, headers=None):
    data = json.dumps(body, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(data)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length > 65536:
        raise ValueError("payload_too_large")
    if length == 0:
        raise ValueError("empty_body")
    value = json.loads(handler.rfile.read(length))
    if not isinstance(value, dict):
        raise ValueError("expected_json_object")
    return value


def log(service, action, correlation_id, **fields):
    print(json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "service": service, "action": action, "correlation_id": correlation_id,
                      **fields}), flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def serve(handler, default_port):
    port = int(os.getenv("PORT", str(default_port)))
    host = os.getenv("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), handler)
    print(f"{handler.__module__} ready on {port}", flush=True)
    server.serve_forever()
