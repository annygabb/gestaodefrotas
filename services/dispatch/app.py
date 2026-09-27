import json
import os
import socket
import socketserver
import threading
import time

from common.http import Handler, log, respond, serve
from common.messaging import consume, publish

INSTANCE = os.getenv("INSTANCE", "dispatch-a")
PEER_HOST = os.getenv("PEER_HOST", "127.0.0.1")
PEER_PORT = int(os.getenv("PEER_PORT", "8302"))
P2P_PORT = int(os.getenv("P2P_PORT", "8301"))
FLEET_HOST = os.getenv("FLEET_HOST", "localhost")
FLEET_PORT = int(os.getenv("FLEET_PORT", "8200"))
CACHE = {}
LOCK = threading.RLock()
PEER_SEEN = False


def exchange(host, port, message):
    with socket.create_connection((host, port), timeout=2) as connection:
        connection.settimeout(2)
        connection.sendall((json.dumps(message) + "\n").encode())
        with connection.makefile("r") as stream:
            line = stream.readline(65536)
            if not line:
                raise ConnectionError("empty_tcp_response")
            return json.loads(line)


class PeerTCP(socketserver.StreamRequestHandler):
    def handle(self):
        global PEER_SEEN
        try:
            message = json.loads(self.rfile.readline(65536))
            if message.get("action") not in ("sync", "hello"):
                raise ValueError("unknown_peer_action")
            with LOCK:
                PEER_SEEN = True
                if message["action"] == "sync":
                    CACHE[message["request_id"]] = message["vehicle_id"]
                    log(INSTANCE, "peer_cache_synced", message.get("correlation_id", "-"),
                        request_id=message["request_id"])
                answer = {"peer": INSTANCE, "cache_size": len(CACHE)}
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            answer = {"error": str(exc)}
        self.wfile.write((json.dumps(answer) + "\n").encode())


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def discover():
    global PEER_SEEN
    while True:
        try:
            response = exchange(PEER_HOST, PEER_PORT, {"action": "hello", "from": INSTANCE})
            PEER_SEEN = "peer" in response
            if PEER_SEEN:
                log(INSTANCE, "peer_discovered", "-", peer=response["peer"])
        except OSError:
            PEER_SEEN = False
        time.sleep(5)


def on_request(message):
    event = message["event"]
    rid, cargo = event["request_id"], event["cargo_kg"]
    if not isinstance(cargo, (float, int)) or isinstance(cargo, bool):
        raise ValueError("invalid_cargo")
    decision = exchange(FLEET_HOST, FLEET_PORT, {"action": "reserve", "request_id": rid,
                        "cargo_kg": cargo, "correlation_id": message["correlation_id"]})
    if decision.get("status") not in ("ASSIGNED", "REJECTED"):
        raise ValueError("fleet_response_invalid")
    # Cross-instance cache is an actual direct P2P TCP exchange; fleet DB remains authoritative.
    if decision["status"] == "ASSIGNED":
        with LOCK:
            CACHE[rid] = decision["vehicle_id"]
        try:
            exchange(PEER_HOST, PEER_PORT, {"action": "sync", "request_id": rid,
                     "vehicle_id": decision["vehicle_id"], "correlation_id": message["correlation_id"]})
        except OSError as exc:
            log(INSTANCE, "peer_sync_pending", message["correlation_id"], error=str(exc))
    publish("assignment.decided", {"request_id": rid, **decision}, message["correlation_id"])
    log(INSTANCE, "assignment_decided", message["correlation_id"], request_id=rid, **decision)


class API(Handler):
    def do_GET(self):
        if self.path in ("/health", "/peer-state"):
            with LOCK:
                return respond(self, 200, {"instance": INSTANCE, "peer_seen": PEER_SEEN, "cache": dict(CACHE)})
        respond(self, 404, {"error": "not_found"})


if __name__ == "__main__":
    tcp = TCPServer((os.getenv("HOST", "0.0.0.0"), P2P_PORT), PeerTCP)
    threading.Thread(target=tcp.serve_forever, daemon=True).start()
    threading.Thread(target=discover, daemon=True).start()
    threading.Thread(target=lambda: consume("dispatch", on_request, INSTANCE), daemon=True).start()
    serve(API, 8104)
