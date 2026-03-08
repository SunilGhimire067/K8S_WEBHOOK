import asyncio
import inspect
import sys
from pathlib import Path

# Add webhook/ to sys.path so we can import mcp_server
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "webhook"))

from mcp_server import (  # noqa: E402
    analyze_event,
    apply_fix,
    get_cluster_info,
    get_event,
    get_event_summary,
    get_jvm_details,
    get_network_status,
    list_events,
    mark_resolved,
    trace_resource_usage,
)

TOOL_FUNCTIONS = {
    "list_events": list_events,
    "get_event": get_event,
    "analyze_event": analyze_event,
    "get_cluster_info": get_cluster_info,
    "apply_fix": apply_fix,
    "mark_resolved": mark_resolved,
    "get_event_summary": get_event_summary,
    "trace_resource_usage": trace_resource_usage,
    "get_jvm_details": get_jvm_details,
    "get_network_status": get_network_status,
}


class StreamingCtx:
    """Context that pushes progress/log events into an async queue for SSE streaming."""

    def __init__(self, queue: asyncio.Queue | None = None):
        self._queue = queue

    async def _emit(self, level: str, message: str):
        if self._queue:
            await self._queue.put({"type": "progress", "level": level, "message": message})

    async def info(self, msg: str) -> None:
        await self._emit("info", msg)

    async def warning(self, msg: str) -> None:
        await self._emit("warning", msg)

    async def error(self, msg: str) -> None:
        await self._emit("error", msg)

    async def debug(self, msg: str) -> None:
        await self._emit("debug", msg)

    async def report_progress(self, current: int, total: int) -> None:
        if self._queue and total > 0:
            await self._queue.put({
                "type": "progress",
                "level": "progress",
                "message": f"{current}/{total}",
                "current": current,
                "total": total,
            })


async def execute_tool(
    name: str, arguments: dict, queue: asyncio.Queue | None = None,
) -> str:
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return f"Error: Unknown tool '{name}'"
    try:
        # MCP tools are async — strip ctx param and inject our streaming ctx
        arguments.pop("ctx", None)
        ctx = StreamingCtx(queue)
        result = func(ctx=ctx, **arguments)
        if inspect.isawaitable(result):
            result = await result
        # Truncate very large results to avoid context overflow
        if len(result) > 8000:
            result = result[:8000] + "\n\n... (truncated)"
        return result
    except Exception as e:
        return f"Error executing {name}: {e}"
