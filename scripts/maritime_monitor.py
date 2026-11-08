"""Maritime's HTTP contract for deterministic calendar checks, without an LLM."""

import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from uuid import uuid4


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Monitor:
    def __init__(self, state_path, group="public"):
        self.path = Path(state_path)
        self.group = group
        self.lock = Lock()
        self.running = False
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {"status": "idle"}
        if self.state.get("status") == "running":
            self.state["status"] = "interrupted"

    def status(self):
        with self.lock:
            return {**self.state, "running": self.running}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state), encoding="utf-8")
        temporary.replace(self.path)

    def start(self):
        with self.lock:
            if self.running:
                return {"response": "A calendar check is already running.", **self.state}
            self.state = {"status": "running", "check_id": str(uuid4()), "started_at": timestamp()}
            self._save()
            self.running = True
            Thread(target=self._check, daemon=True).start()
            return {"response": "Calendar check started. Read /status for its result.", **self.state}

    def _check(self):
        result = {"status": "failed"}
        try:
            process = subprocess.run(
                [sys.executable, "-m", "scripts.check_sources", *(["--group", "instagram"] if self.group == "instagram" else [])],
                capture_output=True, text=True, timeout=3600 if self.group == "instagram" else 600,
            )
            if process.stdout.strip():
                counts = json.loads(process.stdout.strip().splitlines()[-1])
                result["counts"] = {key: counts[key] for key in
                                    ("checked", "submitted", "unchanged", "review", "failed")}
                if "sources" in counts:
                    result["sources"] = counts["sources"]
            if process.returncode == 0:
                result["status"] = "succeeded"
            else:
                result["error"] = "checker_failed"
                # The checker emits only error types and HTTP codes; never relay raw logs or URLs.
                result["details"] = [line for line in process.stderr.splitlines()
                                     if line.startswith(("Feed check failed:", "Listing "))][-10:]
        except subprocess.TimeoutExpired:
            result["error"] = "checker_timeout"
        except (OSError, ValueError, KeyError, TypeError):
            result["error"] = "checker_result_unavailable"
        with self.lock:
            self.state.update(result, completed_at=timestamp())
            try:
                self._save()
            finally:
                self.running = False


def handler_for(monitor, instagram=None):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"status": "ok", "worker": "calendar", "uses_llm": False})
            elif self.path == "/status":
                self.reply(200, {**monitor.status(), **({"instagram": instagram.status()} if instagram else {})})
            elif self.path == "/schedules":
                # Schedules are managed explicitly through Maritime triggers after a proven check.
                self.reply(200, [])
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != "/chat":
                self.reply(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError()
                body = json.loads(self.rfile.read(length))
                message = body.get("message", "").strip().lower()
            except (ValueError, AttributeError, UnicodeError):
                self.reply(400, {"error": "invalid_request"})
                return
            if message == "status":
                self.reply(200, {"response": json.dumps(monitor.status())})
            elif message == "instagram status" and instagram:
                self.reply(200, {"response": json.dumps(instagram.status())})
            elif message == "check instagram" and instagram:
                self.reply(200, instagram.start())
            elif message in ("check", "check calendar"):
                self.reply(200, monitor.start())
            else:
                self.reply(200, {"response": "Send 'check' to check the calendar, or 'status' for the last result."})

        def log_message(self, format, *args):
            # Avoid logging request data; operation results are persisted separately.
            pass

    return Handler


def main():
    state_path = os.environ.get("MARITIME_CHECK_STATE", "/data/club-alerts/last-check.json")
    monitor = Monitor(state_path)
    instagram = Monitor(str(Path(state_path).with_name("last-instagram-check.json")), group="instagram")
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "18789"))), handler_for(monitor, instagram))
    server.serve_forever()


if __name__ == "__main__":
    main()
