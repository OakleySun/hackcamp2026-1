"""Read finished Databricks job output and serve the last validated Pulse snapshot."""

import json
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field

from . import config, databricks, service


class Metrics(BaseModel):
    announcements: int = Field(ge=0)
    upcoming_events: int = Field(ge=0)
    event_revisions: int = Field(ge=0)
    venues_placed_by_ai: int = Field(ge=0)
    possible_duplicates: int = Field(ge=0)


class EventResult(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    source_url: str = Field(pattern=r"^https://", max_length=2048)
    building_name: str | None = Field(default=None, max_length=200)
    location_method: str | None = Field(default=None, max_length=40)


class Snapshot(BaseModel):
    refreshed_at: AwareDatetime
    metrics: Metrics
    events: list[EventResult] = Field(max_length=12)


def sync(conn, job_id: str) -> bool:
    cached = conn.execute("SELECT run_id FROM databricks_pulse WHERE job_id=?", (job_id,)).fetchone()
    with databricks._client(timeout=12) as client:
        runs = client.get("/api/2.2/jobs/runs/list",
                          params={"job_id": job_id, "completed_only": "true", "limit": 10}).raise_for_status().json()
        run = next((r for r in runs.get("runs", []) if r.get("state", {}).get("result_state") == "SUCCESS"), None)
        if run is None or (cached and cached["run_id"] == run["run_id"]):
            return False
        details = client.get("/api/2.2/jobs/runs/get",
                             params={"run_id": run["run_id"]}).raise_for_status().json()
        task = next((t for t in details["tasks"] if t["task_key"] == "pipeline"), None)
        if task is None:
            raise ValueError("Pulse pipeline task is missing")
        output = client.get("/api/2.2/jobs/runs/get-output",
                            params={"run_id": task["run_id"]}).raise_for_status().json()["notebook_output"]
        if output.get("truncated"):
            raise ValueError("Pulse job output was truncated")
        snapshot = Snapshot.model_validate_json(output["result"])
    with conn:
        cursor = conn.execute("""
            INSERT INTO databricks_pulse VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET job_id=excluded.job_id, run_id=excluded.run_id,
                refreshed_at=excluded.refreshed_at, payload=excluded.payload
            WHERE julianday(excluded.refreshed_at) > julianday(databricks_pulse.refreshed_at)
            """, (job_id, run["run_id"], snapshot.refreshed_at.isoformat(), snapshot.model_dump_json()))
    return cursor.rowcount == 1


def public_snapshot(conn) -> dict:
    row = conn.execute("SELECT payload FROM databricks_pulse WHERE singleton=1 AND job_id=?",
                       (config.get("DATABRICKS_PULSE_JOB_ID"),)).fetchone()
    if row is None:
        return {"refreshed_at": None, "metrics": None, "events": []}
    snapshot = json.loads(row["payload"])
    today = datetime.now(service.VAN).date().isoformat()
    events = []
    for result in snapshot["events"]:
        event = conn.execute("""
            SELECT e.title, e.local_date, e.local_start, c.display_name AS club_name
            FROM events e JOIN clubs c USING (club_id)
            WHERE e.event_id=? AND e.current_revision=? AND e.state='published' AND e.local_date>=?
              AND EXISTS (SELECT 1 FROM source_announcements a
                          WHERE a.event_id=e.event_id AND a.source_url=? AND a.status='linked')
            """, (result["event_id"], result["revision"], today, result["source_url"])).fetchone()
        if event:
            events.append({**result, **dict(event)})
    return {**snapshot, "events": events}
