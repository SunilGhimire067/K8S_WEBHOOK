import asyncio
import json
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from .auth import require_auth

logger = logging.getLogger("events-api")

# Ensure shared modules (webhook/) are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEBHOOK_DIR = str(PROJECT_ROOT / "webhook")
if WEBHOOK_DIR not in sys.path:
    sys.path.insert(0, WEBHOOK_DIR)

from database import get_db, get_cursor

router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(require_auth)])


@router.get("")
async def list_events(
    severity: str = "all",
    namespace: str = "all",
    search: str = "",
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        query = (
            "SELECT id, event_id, event_type, kind, name, namespace, reason, "
            "message, severity, status, created_at FROM k8s_events WHERE 1=1"
        )
        params: list = []

        if severity != "all":
            query += " AND severity = %s"
            params.append(severity)
        if namespace != "all":
            query += " AND namespace = %s"
            params.append(namespace)
        if search:
            query += " AND (message LIKE %s OR name LIKE %s OR reason LIKE %s)"
            like = f"%{search}%"
            params.extend([like, like, like])

        # Get total count
        count_query = query.replace(
            "SELECT id, event_id, event_type, kind, name, namespace, reason, "
            "message, severity, status, created_at",
            "SELECT COUNT(*) AS cnt",
        )
        cursor.execute(count_query, params)
        total = cursor.fetchone()["cnt"]

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    return {
        "events": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def event_stats():
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute(
            "SELECT severity, COUNT(*) as count FROM k8s_events GROUP BY severity"
        )
        severity_rows = cursor.fetchall()
        cursor.execute(
            "SELECT status, COUNT(*) as count FROM k8s_events GROUP BY status"
        )
        status_rows = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) AS cnt FROM k8s_events")
        total = cursor.fetchone()["cnt"]
    finally:
        conn.close()

    by_severity = {r["severity"]: r["count"] for r in severity_rows}
    by_status = {r["status"]: r["count"] for r in status_rows}

    return {
        "total": total,
        "by_severity": by_severity,
        "by_status": by_status,
    }


@router.get("/stream")
async def event_stream():
    """SSE endpoint — polls DB every 2s for new events."""

    async def generate():
        last_id = 0
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT MAX(id) AS max_id FROM k8s_events")
            row = cursor.fetchone()
            if row and row["max_id"]:
                last_id = row["max_id"]
        finally:
            conn.close()

        while True:
            await asyncio.sleep(2)
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute(
                    "SELECT id, event_id, event_type, kind, name, namespace, reason, "
                    "message, severity, status, created_at "
                    "FROM k8s_events WHERE id > %s ORDER BY id ASC",
                    (last_id,),
                )
                rows = cursor.fetchall()
            finally:
                conn.close()

            for r in rows:
                last_id = r["id"]
                yield f"data: {json.dumps(r)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{event_id}")
async def get_event(event_id: str):
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute(
            "SELECT * FROM k8s_events WHERE event_id = %s", (event_id,)
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Event not found")

    event = dict(row)
    try:
        event["raw_payload"] = json.loads(event.get("raw_payload", "{}"))
    except (json.JSONDecodeError, TypeError):
        pass
    return event
