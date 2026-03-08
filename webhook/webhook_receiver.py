"""
Kubernetes Webhook Receiver (FastAPI)

Receives K8s admission webhook calls and event notifications,
stores them in a shared MySQL DB that the MCP server reads from.
"""

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from database import get_db, get_cursor, wait_for_db, init_db

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOG_LEVEL = logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("webhook-receiver")


# ---------------------------------------------------------------------------
# Severity classification
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
    "Warning": "warning",
    "Normal": "info",
}


def classify_severity(reason: str | None, event_type: str | None) -> str:
    if reason and reason in SEVERITY_MAP:
        return SEVERITY_MAP[reason]
    if event_type == "Warning":
        return "warning"
    return "info"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "healthy"
    timestamp: str
    total_events: int


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    wait_for_db()
    init_db()
    logger.info("Webhook receiver started")
    yield
    logger.info("Webhook receiver shutting down")


app = FastAPI(
    title="K8s Webhook Receiver",
    description="Receives Kubernetes events and admission webhooks, "
    "stores them for MCP-based analysis via Claude Desktop.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helper – persist an event
# ---------------------------------------------------------------------------
def store_event(payload: dict[str, Any], event_type: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()

    # Extract useful metadata regardless of shape
    metadata = payload.get("metadata", {}) or {}
    involved_obj = payload.get("involvedObject", {}) or {}

    kind = involved_obj.get("kind") or payload.get("kind", "Unknown")
    name = (
        involved_obj.get("name")
        or metadata.get("name")
        or payload.get("name", "unknown")
    )
    namespace = (
        involved_obj.get("namespace")
        or metadata.get("namespace")
        or payload.get("namespace", "default")
    )
    reason = payload.get("reason", "")
    message = payload.get("message", "")
    severity = classify_severity(reason, payload.get("type"))

    event_id = hashlib.sha256(
        f"{kind}:{namespace}:{name}:{reason}:{message}:{now}".encode()
    ).hexdigest()[:16]

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute(
            """
            INSERT IGNORE INTO k8s_events
                (event_id, event_type, kind, name, namespace,
                 reason, message, severity, raw_payload, status,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'new', %s, %s)
            """,
            (
                event_id,
                event_type,
                kind,
                name,
                namespace,
                reason,
                message,
                severity,
                json.dumps(payload),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(
        "Stored event %s  [%s] %s/%s – %s: %s",
        event_id,
        severity,
        namespace,
        name,
        reason,
        message[:120],
    )
    return {
        "event_id": event_id,
        "severity": severity,
        "kind": kind,
        "name": name,
        "namespace": namespace,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("SELECT COUNT(*) AS cnt FROM k8s_events")
        row = cursor.fetchone()
        total = row["cnt"] if row else 0
    finally:
        conn.close()
    return HealthResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_events=total,
    )


@app.post("/webhook/event")
async def receive_event(request: Request):
    """Receive a Kubernetes Event object (e.g. from kube-event-exporter)."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    result = store_event(payload, event_type="k8s-event")
    return {"status": "accepted", **result}


@app.post("/webhook/admission")
async def receive_admission(request: Request):
    """
    Receive a Kubernetes Admission Webhook review request.
    Always ALLOWS the request (non-blocking / audit mode) and
    stores it for analysis.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    admission_request = payload.get("request", {})
    uid = admission_request.get("uid", "unknown")

    store_event(
        {
            **admission_request,
            "kind": admission_request.get("kind", {}).get("kind", "Unknown"),
            "name": admission_request.get("name", "unknown"),
            "namespace": admission_request.get("namespace", "default"),
            "reason": "AdmissionReview",
            "message": f"Admission review for {admission_request.get('operation', '?')} "
            f"on {admission_request.get('kind', {}).get('kind', '?')}",
        },
        event_type="admission",
    )

    # Always allow – this is audit / analysis mode
    return {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "response": {
            "uid": uid,
            "allowed": True,
        },
    }


@app.post("/webhook/alert")
async def receive_alert(request: Request):
    """
    Generic alert endpoint (e.g. from Prometheus Alertmanager).
    Accepts any JSON payload.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    alerts = payload.get("alerts", [payload])
    results = []
    for alert in alerts:
        alert.setdefault("reason", alert.get("labels", {}).get("alertname", "Alert"))
        alert.setdefault(
            "message",
            alert.get("annotations", {}).get("summary", json.dumps(alert)[:200]),
        )
        results.append(store_event(alert, event_type="alert"))

    return {"status": "accepted", "stored": len(results), "events": results}


# ---------------------------------------------------------------------------
# Run with:  uvicorn webhook_receiver:app --host 0.0.0.0 --port 8000
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
