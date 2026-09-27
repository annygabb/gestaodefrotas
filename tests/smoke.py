"""End-to-end local verification using only the Python standard library."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8100"


def call(method, url, body=None, headers=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def until(condition, seconds=18):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = condition()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(.2)
    raise AssertionError("timeout waiting for expected state")


def main():
    processes = []
    with tempfile.TemporaryDirectory(prefix="arp01-") as tmp:
        output = open(os.path.join(tmp, "service.log"), "w+")
        env = dict(os.environ, PYTHONPATH=str(ROOT), DATA_DIR=tmp, API_KEY="smoke-secret",
                   BROKER_URL="http://127.0.0.1:8101", REQUESTS_URL="http://127.0.0.1:8102",
                   FLEET_HOST="127.0.0.1")

        def start(service, **extra):
            processes.append(subprocess.Popen([sys.executable, "-m", f"services.{service}.app"],
                          cwd=ROOT, env={**env, **extra}, stdout=output, stderr=subprocess.STDOUT))

        try:
            start("broker")
            start("requests")
            start("fleet")
            start("notifications")
            start("dispatch", INSTANCE="dispatch-a", PORT="8104", P2P_PORT="8301", PEER_PORT="8302")
            start("dispatch", INSTANCE="dispatch-b", PORT="8105", P2P_PORT="8302", PEER_PORT="8301")
            start("gateway")
            until(lambda: call("GET", BASE + "/health")[0] == 200)
            until(lambda: call("GET", "http://127.0.0.1:8104/peer-state")[1]["peer_seen"])
            until(lambda: call("GET", "http://127.0.0.1:8105/peer-state")[1]["peer_seen"])

            assert call("POST", BASE + "/requests", {"origin": "A", "destination": "B", "cargo_kg": 8})[0] == 401
            headers = {"X-API-Key": "smoke-secret"}
            assert call("POST", BASE + "/requests", {"origin": "Anapolis", "destination": "Goiania", "cargo_kg": -3}, headers)[0] == 400
            assert call("GET", BASE + "/requests/00000000-0000-0000-0000-000000000000", headers=headers)[0] == 404

            def create(weight):
                status, value = call("POST", BASE + "/requests",
                    {"origin": "Anapolis, GO", "destination": "Goiania, GO", "cargo_kg": weight}, headers)
                assert status == 202 and value["status"] == "CREATED", (status, value)
                return value

            def terminal(item):
                return until(lambda: (lambda row: row if row["status"] in ("ASSIGNED", "REJECTED") else None)(
                    call("GET", BASE + "/requests/" + item["request_id"], headers=headers)[1]))

            first = create(480)
            result = terminal(first)
            assert result["status"] == "ASSIGNED" and result["vehicle_id"] == "CAM-001", result
            assert result["correlation_id"] == first["correlation_id"]
            second = create(1400)
            assert terminal(second)["vehicle_id"] == "CAM-002"
            third = create(9999)
            assert terminal(third)["status"] == "REJECTED"
            until(lambda: len(call("GET", "http://127.0.0.1:8106/notifications/" + first["request_id"])[1]["notifications"]) >= 2)
            until(lambda: first["request_id"] in call("GET", "http://127.0.0.1:8104/peer-state")[1]["cache"])
            until(lambda: first["request_id"] in call("GET", "http://127.0.0.1:8105/peer-state")[1]["cache"])

            # Inject malformed event to verify bounded NACK retries and DLQ.
            code, _ = call("POST", "http://127.0.0.1:8101/publish", {"topic": "request.created",
                            "event": {"request_id": "malformed"}, "correlation_id": "test-dlq"})
            assert code == 201
            dead = until(lambda: (lambda rows: rows if any(x["correlation_id"] == "test-dlq"
                for x in rows) else None)(call("GET", "http://127.0.0.1:8101/dlq")[1]["messages"]))
            assert any(x["attempts"] == 3 for x in dead)
            print("PASS: auth, validation, REST status, 2 dispatch peers, TCP reservation, notifications, DLQ")
            print(json.dumps({"assigned": result, "rejected": third["request_id"], "dlq": len(dead)}, indent=2))
        except Exception:
            output.flush()
            output.seek(0)
            print(output.read()[-12000:], file=sys.stderr)
            raise
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            output.close()


if __name__ == "__main__":
    main()
