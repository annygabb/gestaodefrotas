import json
import threading

from common.http import Handler, database, log, respond, serve
from common.messaging import consume


def init():
    with database("notifications.sqlite") as db:
        db.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL, topic TEXT NOT NULL,
            correlation_id TEXT NOT NULL, UNIQUE(request_id,topic))""")


def on_event(message):
    rid = message["event"]["request_id"]
    with database("notifications.sqlite") as db:
        db.execute("INSERT OR IGNORE INTO notifications(request_id,topic,correlation_id) VALUES (?,?,?)",
                   (rid, message["topic"], message["correlation_id"]))
    log("notifications", "notification_recorded", message["correlation_id"], request_id=rid,
        topic=message["topic"])


class API(Handler):
    def do_GET(self):
        if self.path == "/health":
            return respond(self, 200, {"status": "ok"})
        if self.path.startswith("/notifications/"):
            rid = self.path[len("/notifications/"):]
            with database("notifications.sqlite") as db:
                rows = db.execute("SELECT * FROM notifications WHERE request_id=? ORDER BY id", (rid,)).fetchall()
                return respond(self, 200, {"notifications": [dict(r) for r in rows]})
        respond(self, 404, {"error": "not_found"})


if __name__ == "__main__":
    init()
    threading.Thread(target=lambda: consume("notifications", on_event, "notifications"), daemon=True).start()
    serve(API, 8106)
