import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Ensure shared modules (database, mcp_server) are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEBHOOK_DIR = str(PROJECT_ROOT / "webhook")
if WEBHOOK_DIR not in sys.path:
    sys.path.insert(0, WEBHOOK_DIR)

from database import (
    cleanup_expired_sessions,
    get_db,
    get_cursor,
    init_db,
    seed_admin_user,
    wait_for_db,
)

from . import chat_handler
from .auth import require_auth, router as auth_router
from .chat_handler import handle_chat, handle_chat_stream
from .cluster_api import router as cluster_router
from .events_api import router as events_router
from .settings_api import router as settings_router
from .models import ChatRequest, ChatResponse

logger = logging.getLogger("chat-api")


async def _session_cleanup_loop():
    """Background task: clean expired sessions every 60s."""
    while True:
        try:
            await asyncio.to_thread(cleanup_expired_sessions)
        except Exception:
            logger.exception("Session cleanup failed")
        await asyncio.sleep(60)


# ---------------------------------------------------------------------------
# Background K8s event poller
# ---------------------------------------------------------------------------
SEVERITY_MAP: dict[str, str] = {
    "BackOff": "warning",
    "CrashLoopBackOff": "critical",
    "OOMKilled": "critical",
    "FailedScheduling": "critical",
    "Unhealthy": "warning",
    "FailedMount": "warning",
    "FailedCreate": "critical",
    "ImagePullBackOff": "critical",
    "ErrImagePull": "critical",
    "NodeNotReady": "critical",
    "Evicted": "warning",
    "FailedAttachVolume": "warning",
    "FailedDetachVolume": "warning",
    "DeadlineExceeded": "warning",
}

# Track UIDs we've already stored so we don't re-insert on every poll
_seen_uids: set[str] = set()


def _classify_severity(reason: str | None, event_type: str | None) -> str:
    if reason and reason in SEVERITY_MAP:
        return SEVERITY_MAP[reason]
    if event_type == "Warning":
        return "warning"
    return "info"


def _poll_k8s_events() -> int:
    """Fetch K8s events via kubectl and insert new ones into the DB.
    Returns the number of new events stored."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "events", "--all-namespaces", "-o", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            logger.warning("kubectl get events failed: %s", result.stderr.strip())
            return 0
        data = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.warning("kubectl get events timed out")
        return 0
    except FileNotFoundError:
        logger.warning("kubectl not found — event polling disabled")
        return 0
    except Exception:
        logger.exception("Event poll error")
        return 0

    items = data.get("items", [])
    if not items:
        return 0

    stored = 0
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        for ev in items:
            uid = ev.get("metadata", {}).get("uid", "")
            if not uid or uid in _seen_uids:
                continue

            metadata = ev.get("metadata", {})
            involved = ev.get("involvedObject", {})
            kind = involved.get("kind", "Unknown")
            name = involved.get("name") or metadata.get("name", "unknown")
            namespace = involved.get("namespace") or metadata.get("namespace", "default")
            reason = ev.get("reason", "")
            message = ev.get("message", "")
            event_type = ev.get("type", "Normal")
            severity = _classify_severity(reason, event_type)
            last_ts = ev.get("lastTimestamp") or metadata.get("creationTimestamp", "")

            # Deterministic event_id based on UID so duplicates are impossible
            event_id = hashlib.sha256(uid.encode()).hexdigest()[:16]

            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT IGNORE INTO k8s_events
                    (event_id, event_type, kind, name, namespace,
                     reason, message, severity, raw_payload, status,
                     created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'new', %s, %s)
                """,
                (
                    event_id, "k8s-event", kind, name, namespace,
                    reason, message, severity, json.dumps(ev),
                    last_ts or now, now,
                ),
            )
            if cursor.rowcount > 0:
                stored += 1
            _seen_uids.add(uid)

        conn.commit()
    finally:
        conn.close()

    if stored:
        logger.info("Polled %d new K8s event(s) from cluster", stored)
    return stored


async def _event_poll_loop():
    """Background task: poll K8s events every 30s.
    Disable by setting EVENT_POLL_ENABLED=false (e.g. when using event-exporter)."""
    # Initial delay to let things settle
    await asyncio.sleep(5)
    while True:
        try:
            await asyncio.to_thread(_poll_k8s_events)
        except Exception:
            logger.exception("Event poll loop error")
        await asyncio.sleep(int(os.environ.get("EVENT_POLL_INTERVAL", "30")))


# Set EVENT_POLL_ENABLED=false to disable (e.g. when event-exporter is running)
EVENT_POLL_ENABLED = os.environ.get("EVENT_POLL_ENABLED", "true").lower() != "false"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    wait_for_db()
    init_db()
    seed_admin_user(os.environ.get("SEED_ADMIN_PASSWORD", "admin"))
    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    poll_task = None
    if EVENT_POLL_ENABLED:
        poll_task = asyncio.create_task(_event_poll_loop())
        logger.info("Backend startup complete (event polling enabled)")
    else:
        logger.info("Backend startup complete (event polling disabled — using external exporter)")
    yield
    # Shutdown
    cleanup_task.cancel()
    if poll_task:
        poll_task.cancel()
    for task in [t for t in (cleanup_task, poll_task) if t]:
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Sentinel K8s Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public routes (no auth)
app.include_router(auth_router)

# Protected routes (auth applied via router dependencies)
app.include_router(events_router)
app.include_router(cluster_router)
app.include_router(settings_router)


# ── Protected chat endpoints ──


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(require_auth)])
async def chat(request: ChatRequest):
    messages = [msg.model_dump(exclude_none=True) for msg in request.messages]
    try:
        result = await handle_chat(messages)
    except Exception as e:
        logger.exception("Chat handler failed")
        result = {
            "new_messages": [
                {"role": "assistant", "content": f"Error: {e}"}
            ]
        }
    return ChatResponse(**result)


@app.post("/api/chat/stream", dependencies=[Depends(require_auth)])
async def chat_stream(request: ChatRequest):
    """SSE streaming chat endpoint — sends progress, tool_start, message, and done events."""
    messages = [msg.model_dump(exclude_none=True) for msg in request.messages]

    async def generate():
        try:
            async for event in handle_chat_stream(messages):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.exception("Streaming chat failed")
            yield f"data: {json.dumps({'type': 'message', 'data': {'role': 'assistant', 'content': f'Error: {e}'}})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/skills", dependencies=[Depends(require_auth)])
async def get_skills():
    return {
        "skills": [
            {"id": k, "label": v["label"], "description": v["description"]}
            for k, v in chat_handler.SKILLS.items()
        ]
    }


@app.post("/api/reload", dependencies=[Depends(require_auth)])
async def reload():
    """Reload system_prompt.md and skills.yaml without restarting."""
    chat_handler.reload_config()
    return {"status": "reloaded"}


# ── Public endpoints ──


@app.get("/api/health")
async def health():
    return {"status": "ok"}
