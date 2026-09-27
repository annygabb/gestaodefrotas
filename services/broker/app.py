import json
import os
import threading
import time
import uuid

from common.http import Handler, database, read_json, respond, serve

LOCK = threading.RLock()
SUBSCRIPTIONS = {"dispatch": "request.created", "request-state": "assignment.decided", "notifications": "*"}
MAX_ATTEMPTS = 3


def init():
    with database("broker.sqlite") as db:
        db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, subscription TEXT NOT NULL, topic TEXT NOT NULL,
            event TEXT NOT NULL, correlation_id TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, visible_at REAL NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL)""")


class API(Handler):
    def do_GET(self):
        if self.path == "/health":
            return respond(self, 200, {"status": "ok"})
        if self.path == "/dlq":
            with LOCK, database("broker.sqlite") as db:
                rows = db.execute("SELECT id,subscription,topic,event,correlation_id,attempts FROM messages WHERE state='dead'").fetchall()
                return respond(self, 200, {"messages": [dict(r) for r in rows]})
        respond(self, 404, {"error": "not_found"})

    def do_POST(self):
        try:
            body = read_json(self)
            if self.path == "/publish":
                topic, event, cid = body["topic"], body["event"], body["correlation_id"]
                if not isinstance(topic, str) or not isinstance(event, dict) or not isinstance(cid, str):
                    raise ValueError("invalid_event")
                with LOCK, database("broker.sqlite") as db:
                    for sub, pattern in SUBSCRIPTIONS.items():
                        if pattern == topic or pattern == "*":
                            db.execute("INSERT INTO messages VALUES (?,?,?,?,?,0,?,'pending',?)",
                                       (str(uuid.uuid4()), sub, topic, json.dumps(event), cid, time.time(), time.time()))
                return respond(self, 201, {"published": True})
            if self.path == "/consume":
                sub = body["subscription"]
                if sub not in SUBSCRIPTIONS:
                    return respond(self, 404, {"error": "unknown_subscription"})
                with LOCK, database("broker.sqlite") as db:
                    # An expired lease is delivered again; one worker claims each message.
                    db.execute("BEGIN IMMEDIATE")
                    row = db.execute("""SELECT * FROM messages WHERE subscription=? AND state='pending'
                        AND visible_at<=? ORDER BY created_at LIMIT 1""", (sub, time.time())).fetchone()
                    if row is None:
                        return respond(self, 200, {"empty": True})
                    db.execute("UPDATE messages SET attempts=attempts+1,visible_at=? WHERE id=?",
                               (time.time() + 15, row["id"]))
                    return respond(self, 200, {"message_id": row["id"], "topic": row["topic"],
                                              "event": json.loads(row["event"]), "correlation_id": row["correlation_id"],
                                              "attempt": row["attempts"] + 1})
            if self.path in ("/ack", "/nack"):
                with LOCK, database("broker.sqlite") as db:
                    row = db.execute("SELECT * FROM messages WHERE id=? AND subscription=?",
                                     (body["message_id"], body["subscription"])).fetchone()
                    if row is None:
                        return respond(self, 404, {"error": "message_not_found"})
                    if self.path == "/ack":
                        db.execute("UPDATE messages SET state='acked' WHERE id=?", (row["id"],))
                    else:
                        state = "dead" if row["attempts"] >= MAX_ATTEMPTS else "pending"
                        db.execute("UPDATE messages SET state=?,visible_at=? WHERE id=?",
                                   (state, time.time() + min(2 ** row["attempts"], 8), row["id"]))
                    return respond(self, 200, {"state": "acked" if self.path == "/ack" else state})
            respond(self, 404, {"error": "not_found"})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            respond(self, 400, {"error": str(exc)})


if __name__ == "__main__":
    init()
    serve(API, 8101)
