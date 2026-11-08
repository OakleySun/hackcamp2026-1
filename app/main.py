import hmac
from contextlib import asynccontextmanager, closing
from pathlib import Path

import anyio
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import AwareDatetime

from . import accounts, config, db, enrichment, pulse, service, topic_enrichment
from .extract import ExtractionUnavailable
from .models import (ClaimRequest, Credentials, IntakeRequest, ProfileRequest, ResolveRequest, ResultRequest,
                     SubscribeRequest)

MAX_IMAGE_BYTES = 5 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    with closing(db.connect()) as conn:
        db.init_db(conn)
        service.backfill_event_topics(conn)
    async with anyio.create_task_group() as workers:
        if topic_enrichment.enabled():
            workers.start_soon(topic_enrichment.run)
        try:
            yield
        finally:
            workers.cancel_scope.cancel()


app = FastAPI(title="UBC Club Alerts API", lifespan=lifespan)

# The Quad frontend (frontend/) runs on its own origin and calls the public API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in config.get(
        "CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080,http://localhost:3000,http://localhost:5173",
    ).split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "Authorization"],
)


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _require(env_name: str):
    """Bearer-token check. A missing server-side token denies everything (fail closed)."""
    def dep(authorization: str = Header(default="")):
        expected = config.get(env_name)
        given = authorization.removeprefix("Bearer ").strip()
        if not expected or not hmac.compare_digest(given, expected):
            raise HTTPException(401, "invalid or missing token")
    return dep


require_source = _require("SOURCE_INGEST_TOKEN")
require_reviewer = _require("REVIEWER_TOKEN")
require_enrichment = _require("REVIEW_ENRICHMENT_TOKEN")
require_workflow = _require("WORKFLOW_API_TOKEN")


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ExtractionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except service.NotFound as exc:
        raise HTTPException(404, str(exc))
    except service.ReviewConflict as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


# ------------------------------------------------------------ accounts

def _session_token(authorization: str = Header(default="")) -> str:
    return authorization.removeprefix("Bearer ").strip()


def current_user(token: str = Depends(_session_token), conn=Depends(get_conn)) -> dict:
    try:
        return accounts.user_for_token(conn, token)
    except accounts.AuthError as exc:
        raise HTTPException(401, str(exc))


@app.post("/api/auth/signup", status_code=201)
def signup(body: Credentials, conn=Depends(get_conn)):
    try:
        return accounts.signup(conn, body.email, body.password)
    except accounts.EmailTaken:
        raise HTTPException(409, "an account with this email already exists")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/auth/login")
def login(body: Credentials, conn=Depends(get_conn)):
    try:
        return accounts.login(conn, body.email, body.password)
    except accounts.AuthError as exc:
        raise HTTPException(401, str(exc))


@app.post("/api/auth/logout", status_code=204)
def logout(token: str = Depends(_session_token), conn=Depends(get_conn)):
    accounts.logout(conn, token)


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


@app.put("/api/me/profile")
def save_profile(body: ProfileRequest, user: dict = Depends(current_user), conn=Depends(get_conn)):
    return _run(accounts.save_profile, conn, user["user_id"], body)


# ------------------------------------------------------------ public

@app.get("/health")
def health():
    return {"status": "ok", "mode": config.get("APP_MODE", "demo")}


@app.get("/api/events")
def events(topic: str | None = None, free: bool = False, beginner: bool = False,
           after_4pm: bool = False, include_past: bool = False, conn=Depends(get_conn)):
    return service.list_events(conn, topic, free, beginner, after_4pm, include_past)


@app.get("/api/pulse")
def campus_pulse(conn=Depends(get_conn)):
    return pulse.public_snapshot(conn)


@app.get("/api/events/{event_id}")
def event(event_id: str, conn=Depends(get_conn)):
    ev = service.get_event(conn, event_id)
    if not ev or ev["state"] != "published":
        raise HTTPException(404, "event not found")
    return service.public_event(conn, ev)


@app.get("/api/sources")
def sources(conn=Depends(get_conn)):
    return [dict(r) for r in conn.execute(
        "SELECT source_id, club_id, kind, enabled, last_success_at FROM sources")]


@app.post("/api/subscriptions", status_code=201)
def subscribe(body: SubscribeRequest, conn=Depends(get_conn)):
    if "@" not in body.email:
        raise HTTPException(422, "invalid email")
    try:
        out = service.subscribe(conn, body.email, body.topics, body.want_free, body.want_beginner, body.after_4pm)
    except Exception:
        raise HTTPException(409, "this email is already subscribed")
    # In demo mode the tokens are returned so the flow works without real email.
    return out if config.get("APP_MODE", "demo") == "demo" else {"subscriber_id": out["subscriber_id"]}


@app.post("/verify")
def verify(token: str, conn=Depends(get_conn)):
    if not service.verify(conn, token):
        raise HTTPException(400, "invalid or already used token")
    return {"verified": True}


@app.post("/manage")
def manage(token: str, opt_out: bool = True, conn=Depends(get_conn)):
    if not service.manage(conn, token, opt_out):
        raise HTTPException(404, "invalid token")
    return {"opted_out": opt_out}


# ------------------------------------------------------------ intake and review

@app.post("/api/intake", status_code=202, dependencies=[Depends(require_source)])
def intake(body: IntakeRequest, conn=Depends(get_conn)):
    return _run(service.intake, conn, body.source_id, body.external_id, body.caption, body.source_url,
                observed_at=body.observed_at, candidate=body.candidate)


@app.post("/api/intake/upload", status_code=202, dependencies=[Depends(require_source)])
async def intake_upload(source_id: str = Form(...), external_id: str = Form(...), caption: str = Form(""),
                        source_url: str = Form(""), observed_at: AwareDatetime | None = Form(None),
                        flyer: UploadFile | None = File(None), conn=Depends(get_conn)):
    image, mime = None, None
    if flyer is not None:
        image = await flyer.read(MAX_IMAGE_BYTES + 1)
        if len(image) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "image larger than 5 MB")
        if image.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif image.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        else:
            raise HTTPException(415, "only JPEG or PNG images are accepted")
    return await run_in_threadpool(
        _run, service.intake, conn, source_id, external_id, caption or None, source_url or None,
        image, mime, observed_at,
    )


@app.get("/demo/maritime-feed")
def maritime_demo_feed(room_change: bool = False):
    if config.get("APP_MODE", "demo") != "demo":
        raise HTTPException(404, "demo feed not available")
    item = db.load_fixtures()["announcements"]["C" if room_change else "A"]
    return {"demo": True, "events": [{key: item[key] for key in ("external_id", "source_url", "caption")}]}


@app.get("/api/reviews", dependencies=[Depends(require_reviewer)])
def reviews(conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT r.*, a.caption, a.source_url, a.candidate FROM review_items r "
        "JOIN source_announcements a USING (announcement_id) WHERE r.state='open' ORDER BY r.created_at").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/enrichment/work", dependencies=[Depends(require_enrichment)])
def enrichment_work(conn=Depends(get_conn)):
    return enrichment.work(conn)


@app.post("/api/enrichment/results", dependencies=[Depends(require_enrichment)])
def enrichment_results(body: enrichment.Batch, conn=Depends(get_conn)):
    return _run(enrichment.store, conn, body)


@app.get("/api/reviews/inbox", response_class=HTMLResponse)
def review_inbox():
    return Path(__file__).with_name("review_inbox.html").read_text(encoding="utf-8")


@app.get("/api/reviews/enrichment", dependencies=[Depends(require_reviewer)])
def review_enrichment(conn=Depends(get_conn)):
    return enrichment.inbox(conn)


@app.post("/api/reviews/{review_id}/approve-enrichment", dependencies=[Depends(require_reviewer)])
def approve_enrichment(review_id: str, body: enrichment.Approval, conn=Depends(get_conn)):
    return _run(enrichment.approve, conn, review_id, body.version)


@app.post("/api/reviews/{review_id}/resolve", dependencies=[Depends(require_reviewer)])
def resolve(review_id: str, body: ResolveRequest, conn=Depends(get_conn)):
    return _run(service.resolve_review, conn, review_id, body.decision, body.expected_revision, body.reviewer)


@app.post("/api/demo/reset", dependencies=[Depends(require_reviewer)])
def demo_reset(conn=Depends(get_conn)):
    if config.get("APP_MODE", "demo") != "demo":
        raise HTTPException(403, "reset is only available in demo mode")
    db.reset_db(conn)
    return {"reset": True}


# ------------------------------------------------------------ n8n workflow endpoints

@app.get("/internal/dispatch/{event_id}/{revision}/{kind}", dependencies=[Depends(require_workflow)])
def dispatch(event_id: str, revision: int, kind: str, conn=Depends(get_conn)):
    if kind not in ("new_event", "correction"):
        raise HTTPException(422, "kind must be new_event or correction")
    return _run(service.dispatch_info, conn, event_id, revision, kind)


@app.get("/internal/databricks/status", dependencies=[Depends(require_workflow)])
def databricks_status(conn=Depends(get_conn)):
    """Is the Databricks export enabled, how much is waiting, and when did it last succeed."""
    return service.dbx_status(conn)


@app.get("/internal/outbox/pending", dependencies=[Depends(require_workflow)])
def outbox_pending(conn=Depends(get_conn)):
    """Rows the retry loop should re-dispatch, oldest revision first so a correction never passes its original."""
    return [dict(r) for r in conn.execute(
        "SELECT event_id, revision, kind, attempts FROM event_outbox WHERE status='pending' "
        "ORDER BY event_id, revision")]


@app.post("/internal/deliveries/claim", dependencies=[Depends(require_workflow)])
def claim(body: ClaimRequest, conn=Depends(get_conn)):
    return _run(service.claim, conn, body.subscriber_id, body.event_id, body.revision, body.kind)


@app.post("/internal/deliveries/{delivery_id}/result", dependencies=[Depends(require_workflow)])
def result(delivery_id: str, body: ResultRequest, conn=Depends(get_conn)):
    return _run(service.record_result, conn, delivery_id, body.claim_token, body.outcome, body.provider_msg_id)
