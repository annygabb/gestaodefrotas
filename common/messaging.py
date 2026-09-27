import os
import time
import urllib.error

from common.http import log, request

BROKER = os.getenv("BROKER_URL", "http://localhost:8101")


def publish(topic, event, correlation_id):
    code, data = request("POST", BROKER + "/publish", {
        "topic": topic, "event": event, "correlation_id": correlation_id
    })
    if code != 201:
        raise RuntimeError(f"publish failed: {code} {data}")


def consume(subscription, process, service):
    while True:
        try:
            code, envelope = request("POST", BROKER + "/consume", {"subscription": subscription}, timeout=10)
            if code == 204 or code == 404 or envelope.get("empty"):
                time.sleep(.35)
                continue
            if code != 200:
                raise RuntimeError(f"consume: {code}")
            mid = envelope["message_id"]
            correlation_id = envelope["correlation_id"]
            try:
                process(envelope)
                request("POST", BROKER + "/ack", {"subscription": subscription, "message_id": mid})
                log(service, "message_ack", correlation_id, message_id=mid)
            except Exception as exc:
                log(service, "message_failed", correlation_id, message_id=mid, error=str(exc))
                request("POST", BROKER + "/nack", {"subscription": subscription, "message_id": mid})
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
            log(service, "broker_unavailable", "-", error=str(exc))
            time.sleep(1)
