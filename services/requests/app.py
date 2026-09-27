import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

from common.http import Handler, database, log, read_json, respond, serve
from common.messaging import consume, publish

LOCK = threading.RLock()


def init():
    with database("requests.sqlite") as db:
        db.execute("""CREATE TABLE IF NOT EXISTS requests (
          id TEXT PRIMARY KEY, origin TEXT NOT NULL, destination TEXT NOT NULL,
          cargo_kg REAL NOT NULL, status TEXT NOT NULL,
          vehicle_id TEXT, correlation_id TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS outbox (
          id TEXT PRIMARY KEY, topic TEXT NOT NULL, event TEXT NOT NULL,
          correlation_id TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0)""")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def outbox_loop():
    while True:
        with LOCK, database("requests.sqlite") as db:
            rows = db.execute("SELECT * FROM outbox WHERE published=0 ORDER BY rowid LIMIT 10").fetchall()
            for row in rows:
                try:
                    publish(row["topic"], json.loads(row["event"]), row["correlation_id"])
                    db.execute("UPDATE outbox SET published=1 WHERE id=?", (row["id"],))
                    db.commit()
                    log("requests", "event_published", row["correlation_id"], topic=row["topic"])
                except Exception as exc:
                    log("requests", "publish_retry", row["correlation_id"], error=str(exc))
                    break
        time.sleep(.4)


def on_assignment(message):
    event = message["event"]
    rid, status = event["request_id"], event["status"]
    if status not in ("ASSIGNED", "REJECTED"):
        raise ValueError("invalid_status")
    with LOCK, database("requests.sqlite") as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise ValueError("unknown_request")
        if row["status"] != "CREATED":
            return  # Idempotent replay.
        timestamp = utcnow()
        vehicle = event.get("vehicle_id") if status == "ASSIGNED" else None
        db.execute("UPDATE requests SET status=?,vehicle_id=?,updated_at=? WHERE id=?",
                   (status, vehicle, timestamp, rid))
        db.execute("INSERT INTO outbox VALUES (?,?,?,?,0)",
                   (str(uuid.uuid4()), "request.status_changed", json.dumps({"request_id": rid,
                    "status": status, "vehicle_id": vehicle}), message["correlation_id"]))
    log("requests", "status_changed", message["correlation_id"], request_id=rid, status=status)


class API(Handler):
    def do_GET(self):
        if self.path == "/health":
            return respond(self, 200, {"status": "ok"})
        if not self.path.startswith("/requests/"):
            return respond(self, 404, {"error": "not_found"})
        rid = self.path[len("/requests/"):]
        try:
            uuid.UUID(rid)
        except ValueError:
            return respond(self, 404, {"error": "request_not_found"})
        with database("requests.sqlite") as db:
            row = db.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
            if row:
                respond(self, 200, dict(row))
            else:
                respond(self, 404, {"error": "request_not_found"})

    def do_POST(self):
        if self.path != "/requests":
            return respond(self, 404, {"error": "not_found"})
        try:
            body = read_json(self)
            origin, destination, cargo = body["origin"], body["destination"], body["cargo_kg"]
            if not all(isinstance(x, str) and 2 <= len(x.strip()) <= 120 for x in (origin, destination)):
                raise ValueError("origin_and_destination_must_be_2_to_120_characters")
            if origin.strip().lower() == destination.strip().lower():
                raise ValueError("origin_and_destination_must_differ")
            if isinstance(cargo, bool) or not isinstance(cargo, (int, float)) or not 0 < cargo <= 10000:
                raise ValueError("cargo_kg_must_be_between_0_and_10000")
            raw_cid = self.headers.get("X-Correlation-ID", "")
            try:
                cid = str(uuid.UUID(raw_cid)) if raw_cid else str(uuid.uuid4())
            except ValueError:
                raise ValueError("invalid_correlation_id")
            rid, timestamp = str(uuid.uuid4()), utcnow()
            event = {"request_id": rid, "origin": origin.strip(), "destination": destination.strip(), "cargo_kg": cargo}
            with LOCK, database("requests.sqlite") as db:
                db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?)",
                           (rid, origin.strip(), destination.strip(), cargo, "CREATED", None, cid, timestamp, timestamp))
                db.execute("INSERT INTO outbox VALUES (?,?,?,?,0)",
                           (str(uuid.uuid4()), "request.created", json.dumps(event), cid))
            log("requests", "created", cid, request_id=rid)
            respond(self, 202, {"request_id": rid, "status": "CREATED", "correlation_id": cid})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            respond(self, 400, {"error": str(exc)})


if __name__ == "__main__":
    init()
    threading.Thread(target=outbox_loop, daemon=True).start()
    threading.Thread(target=lambda: consume("request-state", on_assignment, "requests"), daemon=True).start()
    serve(API, 8102)
