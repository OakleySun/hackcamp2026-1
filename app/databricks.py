"""Client for the Databricks SQL Statement Execution API, plus the Bronze MERGE statements.

Nothing here runs inside a request or a SQLite write transaction: only the background export
worker (`scripts/dbx_worker.py`) calls these functions.

Settings: DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID, DATABRICKS_TOKEN (a personal access token or a
service principal token), DATABRICKS_CATALOG (default `workspace`), DATABRICKS_SCHEMA (default
`club_alerts`, giving schemas club_alerts_bronze / _silver / _gold).
"""
from __future__ import annotations

import re
import time

import httpx

from . import config

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatabricksError(Exception):
    """The statement failed or the API could not be reached. Safe to retry later."""


class StatementPending(DatabricksError):
    """The statement is still running after our deadline. Keep its ID and check it later."""

    def __init__(self, statement_id: str):
        super().__init__(f"statement {statement_id} still running")
        self.statement_id = statement_id


def configured() -> bool:
    return all(config.get(k) for k in ("DATABRICKS_HOST", "DATABRICKS_WAREHOUSE_ID", "DATABRICKS_TOKEN"))


def table(layer: str, name: str) -> str:
    """Fully qualified name, e.g. workspace.club_alerts_bronze.source_announcements."""
    catalog = config.get("DATABRICKS_CATALOG", "workspace")
    prefix = config.get("DATABRICKS_SCHEMA", "club_alerts")
    for part in (catalog, prefix, layer, name):
        if not _IDENT.match(part):
            raise DatabricksError(f"invalid identifier {part!r}")
    return f"{catalog}.{prefix}_{layer}.{name}"


def _client(timeout: float = 30) -> httpx.Client:
    host = config.get("DATABRICKS_HOST").rstrip("/")
    base = host if host.startswith("https://") else "https://" + host.removeprefix("http://")
    return httpx.Client(base_url=base, timeout=timeout,
                        headers={"Authorization": f"Bearer {config.get('DATABRICKS_TOKEN')}"})


def _check(data: dict) -> list[list]:
    state = data["status"]["state"]
    if state != "SUCCEEDED":
        message = (data["status"].get("error") or {}).get("message", state)
        raise DatabricksError(f"{state}: {message[:300]}")
    return (data.get("result") or {}).get("data_array") or []


def execute(statement: str, params: dict | None = None, deadline_s: float = 50) -> list[list]:
    """Run one parameterized statement (named :params, values sent as strings, None = NULL).
    Returns rows. Raises StatementPending with the statement ID if it outlives the deadline."""
    if not configured():
        raise DatabricksError("Databricks is not configured")
    body = {
        "warehouse_id": config.get("DATABRICKS_WAREHOUSE_ID"),
        "statement": statement,
        "parameters": [{"name": k, **({} if v is None else {"value": str(v)})} for k, v in (params or {}).items()],
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
        "disposition": "INLINE",
        "format": "JSON_ARRAY",
    }
    stop = time.monotonic() + deadline_s
    try:
        with _client() as http:
            resp = http.post("/api/2.0/sql/statements", json=body)
            resp.raise_for_status()
            data = resp.json()
            while data["status"]["state"] not in TERMINAL:
                if time.monotonic() > stop:
                    raise StatementPending(data["statement_id"])
                time.sleep(1)
                resp = http.get(f"/api/2.0/sql/statements/{data['statement_id']}")
                resp.raise_for_status()
                data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise DatabricksError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise DatabricksError(f"connection failed: {type(exc).__name__}") from exc
    return _check(data)


def statement_state(statement_id: str) -> str:
    """State of an earlier statement: PENDING, RUNNING, SUCCEEDED, FAILED, CANCELED or CLOSED."""
    try:
        with _client(timeout=15) as http:
            resp = http.get(f"/api/2.0/sql/statements/{statement_id}")
            if resp.status_code == 404:
                return "CLOSED"
            resp.raise_for_status()
            return resp.json()["status"]["state"]
    except httpx.HTTPError as exc:
        raise DatabricksError(f"connection failed: {type(exc).__name__}") from exc


# ------------------------------------------------------------------ Bronze projections (idempotent)

def merge_announcement_sql() -> str:
    """Upsert one source version. A delayed retry with an older projection_version is ignored,
    so it can never overwrite a newer review outcome."""
    return f"""
MERGE INTO {table('bronze', 'source_announcements')} t
USING (SELECT :announcement_id AS announcement_id, :source_id AS source_id, :external_id AS external_id,
              :source_url AS source_url, CAST(:detected_at AS TIMESTAMP) AS detected_at, :status AS status,
              :caption AS caption, :candidate_json AS candidate_json, :evidence_json AS evidence_json,
              :event_id AS event_id, CAST(:projection_version AS BIGINT) AS projection_version) s
ON t.announcement_id = s.announcement_id
WHEN MATCHED AND (t.projection_version IS NULL OR s.projection_version > t.projection_version) THEN UPDATE SET
  source_id = s.source_id, external_id = s.external_id, source_url = s.source_url, detected_at = s.detected_at,
  status = s.status, caption = s.caption, candidate_json = s.candidate_json, evidence_json = s.evidence_json,
  event_id = s.event_id, projection_version = s.projection_version, ingested_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT
  (announcement_id, source_id, external_id, source_url, detected_at, status, caption, candidate_json,
   evidence_json, event_id, projection_version, ingested_at)
  VALUES (s.announcement_id, s.source_id, s.external_id, s.source_url, s.detected_at, s.status, s.caption,
          s.candidate_json, s.evidence_json, s.event_id, s.projection_version, current_timestamp())"""


def merge_revision_sql() -> str:
    """Event revisions are immutable, keyed by (event_id, revision): insert once, never update."""
    return f"""
MERGE INTO {table('bronze', 'event_revisions')} t
USING (SELECT :event_id AS event_id, CAST(:revision AS INT) AS revision, :club_id AS club_id,
              :snapshot_json AS snapshot_json, :changed_json AS changed_json, :reason AS reason,
              CAST(:created_at AS TIMESTAMP) AS created_at) s
ON t.event_id = s.event_id AND t.revision = s.revision
WHEN NOT MATCHED THEN INSERT
  (event_id, revision, club_id, snapshot_json, changed_json, reason, created_at, ingested_at)
  VALUES (s.event_id, s.revision, s.club_id, s.snapshot_json, s.changed_json, s.reason, s.created_at,
          current_timestamp())"""


def export(kind: str, payload: dict) -> None:
    if kind == "announcement":
        execute(merge_announcement_sql(), payload)
    elif kind == "revision":
        execute(merge_revision_sql(), payload)
    else:
        raise DatabricksError(f"unknown export kind {kind!r}")
