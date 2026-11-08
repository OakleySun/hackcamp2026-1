"""The custom Maritime worker acknowledges slow checks without invoking a model."""

import json
import subprocess
from http.server import ThreadingHTTPServer
from threading import Event, Thread
from time import monotonic, sleep

import httpx

from scripts import maritime_monitor


def test_monitor_contract_coalesces_checks_and_persists_result(tmp_path, monkeypatch):
    release = Event()
    calls = []
    counts = {"checked": 16, "submitted": 0, "unchanged": 16, "review": 0, "failed": 0}
    sources = [{"source_id": "src-csss-affiliates", "status": "succeeded", **counts}]

    def check(command, **kwargs):
        calls.append(command)
        assert release.wait(5)
        return subprocess.CompletedProcess(command, 0, json.dumps({**counts, "sources": sources}), "")

    monkeypatch.setattr(maritime_monitor.subprocess, "run", check)
    state_path = tmp_path / "last-check.json"
    monitor = maritime_monitor.Monitor(state_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), maritime_monitor.handler_for(monitor))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", timeout=2) as client:
            assert client.get("/health").json()["uses_llm"] is False
            assert not calls and not state_path.exists()
            first = client.post("/chat", json={"message": "check", "source": "scheduled"}).json()
            assert first["status"] == "running"
            second = client.post("/chat", json={"message": "check"}).json()
            assert second["check_id"] == first["check_id"]
            release.set()
            deadline = monotonic() + 3
            while monitor.status()["running"] and monotonic() < deadline:
                sleep(0.01)
            result = client.get("/status").json()
            assert result["status"] == "succeeded" and result["counts"] == counts
            assert result["sources"] == sources
            assert len(calls) == 1 and calls[0][-2:] == ["-m", "scripts.check_sources"]
            assert maritime_monitor.Monitor(state_path).status()["counts"] == counts
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
