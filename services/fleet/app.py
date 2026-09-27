import json
import os
import socketserver
import threading

from common.http import Handler, database, log, respond, serve

LOCK = threading.RLock()


def init():
    with database("fleet.sqlite") as db:
        db.execute("CREATE TABLE IF NOT EXISTS vehicles (id TEXT PRIMARY KEY, capacity_kg REAL NOT NULL, status TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS allocations (request_id TEXT PRIMARY KEY, vehicle_id TEXT NOT NULL)")
        for vid, capacity in (("CAM-001", 500), ("CAM-002", 1500), ("CAM-003", 5000)):
            db.execute("INSERT OR IGNORE INTO vehicles VALUES (?,?,?)", (vid, capacity, "AVAILABLE"))


class TCP(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            command = json.loads(self.rfile.readline(65536))
            rid, cargo = command["request_id"], command["cargo_kg"]
            if command.get("action") != "reserve" or not isinstance(cargo, (int, float)) or isinstance(cargo, bool):
                raise ValueError("invalid_reservation")
            with LOCK, database("fleet.sqlite") as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT vehicle_id FROM allocations WHERE request_id=?", (rid,)).fetchone()
                if existing:
                    vehicle, status = existing["vehicle_id"], "ASSIGNED"
                else:
                    found = db.execute("""SELECT id FROM vehicles WHERE status='AVAILABLE' AND capacity_kg>=?
                                            ORDER BY capacity_kg,id LIMIT 1""", (cargo,)).fetchone()
                    vehicle, status = (found["id"], "ASSIGNED") if found else (None, "REJECTED")
                    if found:
                        db.execute("UPDATE vehicles SET status='RESERVED' WHERE id=?", (vehicle,))
                        db.execute("INSERT INTO allocations VALUES (?,?)", (rid, vehicle))
            result = {"status": status, "vehicle_id": vehicle}
            log("fleet", "reserve", command.get("correlation_id", "-"), request_id=rid, **result)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            result = {"error": str(exc)}
        self.wfile.write((json.dumps(result) + "\n").encode())


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class API(Handler):
    def do_GET(self):
        if self.path == "/health":
            return respond(self, 200, {"status": "ok"})
        if self.path == "/vehicles":
            with database("fleet.sqlite") as db:
                return respond(self, 200, {"vehicles": [dict(r) for r in db.execute("SELECT * FROM vehicles")]})
        respond(self, 404, {"error": "not_found"})


if __name__ == "__main__":
    init()
    tcp = TCPServer((os.getenv("HOST", "0.0.0.0"), int(os.getenv("TCP_PORT", "8200"))), TCP)
    threading.Thread(target=tcp.serve_forever, daemon=True).start()
    serve(API, 8103)
