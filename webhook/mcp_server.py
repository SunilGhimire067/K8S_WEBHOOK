"""
MCP Server for Kubernetes Event Analysis

Connects to the same MySQL DB as the webhook receiver.
Exposes tools that Claude Desktop can call to:
  - list_events      : Browse recent K8s events with filters
  - get_event        : Get full details of a single event
  - analyze_event    : Return context + suggested fix for an event
  - get_cluster_info : Fetch live cluster state via kubectl
  - apply_fix        : Run a kubectl command to remediate (requires confirmation)
"""

import json
import logging
import subprocess
from datetime import datetime, timezone

from mcp.server.fastmcp import Context, FastMCP

from database import get_db, get_cursor

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("mcp-k8s")


class _NoOpCtx:
    """Stub context used when tools are called outside MCP (e.g. from chat backend)."""
    async def info(self, msg: str) -> None: pass
    async def warning(self, msg: str) -> None: pass
    async def error(self, msg: str) -> None: pass
    async def debug(self, msg: str) -> None: pass
    async def report_progress(self, current: int, total: int) -> None: pass

_noop_ctx = _NoOpCtx()

mcp = FastMCP(
    "k8s-event-analyzer",
    instructions=(
        "Kubernetes event analysis and remediation tools for Claude Desktop. "
        "IMPORTANT ROUTING RULE: When the user says 'ai analyze' followed by a pod name or event, "
        "call the analyze_event tool with use_sampling=True for AI-powered deep analysis. "
        "For regular analysis requests, call analyze_event with use_sampling=False."
    ),
)


# ---------------------------------------------------------------------------
# Tool: list_events
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_events(
    status: str = "all",
    severity: str = "all",
    namespace: str = "all",
    limit: int = 20,
    ctx: Context = None,
) -> str:
    """
    List recent Kubernetes events stored by the webhook receiver.

    Args:
        status:    Filter by status – 'new', 'analyzed', 'resolved', or 'all'
        severity:  Filter by severity – 'info', 'warning', 'critical', or 'all'
        namespace: Filter by K8s namespace, or 'all'
        limit:     Max events to return (default 20)
    """
    ctx = ctx or _noop_ctx
    await ctx.info(f"Listing events (status={status}, severity={severity}, namespace={namespace}, limit={limit})")
    await ctx.report_progress(0, 3)

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        query = "SELECT id, event_id, event_type, kind, name, namespace, reason, message, severity, status, created_at FROM k8s_events WHERE 1=1"
        params: list = []

        if status != "all":
            query += " AND status = %s"
            params.append(status)
        if severity != "all":
            query += " AND severity = %s"
            params.append(severity)
        if namespace != "all":
            query += " AND namespace = %s"
            params.append(namespace)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        await ctx.report_progress(1, 3)
        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    await ctx.report_progress(2, 3)

    if not rows:
        await ctx.warning("No events found matching the given filters.")
        return "No events found matching the given filters."

    events = rows
    summary_lines = [f"Found {len(events)} event(s):\n"]
    for e in events:
        summary_lines.append(
            f"  [{e['severity'].upper():8s}] {e['event_id']}  "
            f"{e['namespace']}/{e['name']} ({e['kind']}) – "
            f"{e['reason']}: {(e['message'] or '')[:100]}"
        )

    await ctx.info(f"Returning {len(events)} event(s)")
    await ctx.report_progress(3, 3)
    return "\n".join(summary_lines) + "\n\n" + json.dumps(events, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_event
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_event(event_id: str, ctx: Context = None) -> str:
    """
    Get the full details of a specific Kubernetes event including the raw payload.

    Args:
        event_id: The short event ID returned by list_events
    """
    ctx = ctx or _noop_ctx
    await ctx.info(f"Fetching event: {event_id}")
    await ctx.report_progress(0, 2)

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute(
            "SELECT * FROM k8s_events WHERE event_id = %s", (event_id,)
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    await ctx.report_progress(1, 2)

    if not row:
        await ctx.warning(f"Event '{event_id}' not found.")
        return f"Event '{event_id}' not found."

    event = dict(row)
    # Parse raw payload for pretty-printing
    try:
        event["raw_payload"] = json.loads(event["raw_payload"])
    except (json.JSONDecodeError, TypeError):
        pass

    await ctx.info(f"Returning details for event {event_id}")
    await ctx.report_progress(2, 2)
    return json.dumps(event, indent=2)


# ---------------------------------------------------------------------------
# Tool: analyze_event
# ---------------------------------------------------------------------------
ANALYSIS_TEMPLATES: dict[str, str] = {
    "CrashLoopBackOff": (
        "## CrashLoopBackOff Analysis\n\n"
        "**Root Causes (most common):**\n"
        "1. Application error / uncaught exception on startup\n"
        "2. Missing config or secrets (env vars, ConfigMap, Secret mounts)\n"
        "3. Liveness probe misconfiguration (probe fires before app is ready)\n"
        "4. Insufficient resources (OOMKilled → CrashLoop)\n\n"
        "**Diagnostic Commands:**\n"
        "```bash\n"
        "kubectl logs {namespace}/{name} --previous\n"
        "kubectl describe pod -n {namespace} {name}\n"
        "kubectl get events -n {namespace} --field-selector involvedObject.name={name}\n"
        "```\n\n"
        "**Suggested Fixes:**\n"
        "- Check previous container logs for the actual error\n"
        "- Verify all required env vars / secrets exist\n"
        "- Increase `initialDelaySeconds` on liveness probe\n"
        "- Increase memory/CPU limits if OOMKilled\n"
    ),
    "OOMKilled": (
        "## OOMKilled Analysis\n\n"
        "The container was killed because it exceeded its memory limit.\n\n"
        "**Diagnostic Commands:**\n"
        "```bash\n"
        "kubectl describe pod -n {namespace} {name}\n"
        "kubectl top pod -n {namespace} {name}\n"
        "```\n\n"
        "**Suggested Fixes:**\n"
        "- Increase `resources.limits.memory` in the pod spec\n"
        "- Profile the application for memory leaks\n"
        "- Add JVM `-Xmx` flags if Java-based\n"
        "- Consider horizontal scaling instead of vertical\n"
    ),
    "ImagePullBackOff": (
        "## ImagePullBackOff Analysis\n\n"
        "Kubernetes cannot pull the container image.\n\n"
        "**Diagnostic Commands:**\n"
        "```bash\n"
        "kubectl describe pod -n {namespace} {name}\n"
        "kubectl get events -n {namespace} --field-selector reason=Failed\n"
        "```\n\n"
        "**Suggested Fixes:**\n"
        "- Verify the image name and tag exist in the registry\n"
        "- Check `imagePullSecrets` are configured on the pod/service account\n"
        "- Ensure the node can reach the container registry (network policy / firewall)\n"
        "- Try `docker pull <image>` manually from a node\n"
    ),
    "FailedScheduling": (
        "## FailedScheduling Analysis\n\n"
        "The scheduler cannot place the pod on any node.\n\n"
        "**Diagnostic Commands:**\n"
        "```bash\n"
        "kubectl describe pod -n {namespace} {name}\n"
        "kubectl get nodes -o wide\n"
        "kubectl describe nodes | grep -A5 'Allocated resources'\n"
        "```\n\n"
        "**Suggested Fixes:**\n"
        "- Check node resource availability (CPU/memory)\n"
        "- Review nodeSelector / affinity / tolerations\n"
        "- Scale up the cluster or remove resource constraints\n"
        "- Check for PVC binding issues if volumes are involved\n"
    ),
    "Unhealthy": (
        "## Unhealthy Probe Failure Analysis\n\n"
        "A liveness or readiness probe is failing.\n\n"
        "**Diagnostic Commands:**\n"
        "```bash\n"
        "kubectl describe pod -n {namespace} {name}\n"
        "kubectl logs -n {namespace} {name}\n"
        "```\n\n"
        "**Suggested Fixes:**\n"
        "- Verify the probe endpoint is correct and returns 200\n"
        "- Increase `initialDelaySeconds` / `timeoutSeconds`\n"
        "- Check if the application port matches the probe port\n"
        "- Review application startup time\n"
    ),
}

DEFAULT_ANALYSIS = (
    "## General Event Analysis\n\n"
    "**Diagnostic Commands:**\n"
    "```bash\n"
    "kubectl describe {kind_lower} -n {namespace} {name}\n"
    "kubectl logs -n {namespace} {name}  # if applicable\n"
    "kubectl get events -n {namespace} --sort-by='.lastTimestamp'\n"
    "```\n\n"
    "**Next Steps:**\n"
    "- Review the event message for clues\n"
    "- Check related resources (Services, ConfigMaps, Secrets)\n"
    "- Inspect recent deployments or changes\n"
)


@mcp.tool()
async def analyze_event(event_id: str, use_sampling: bool = False, ctx: Context = None) -> str:
    """
    Analyze a Kubernetes event and return diagnostics + suggested fixes.
    Updates the event status to 'analyzed'.

    ROUTING RULE: If the user's message contains 'ai analyze', set use_sampling=True.
    Otherwise default to use_sampling=False (uses built-in templates).

    Args:
        event_id:      The short event ID to analyze
        use_sampling:  If True, uses MCP sampling to get AI-powered analysis.
                       If False (default), uses built-in templates.
    """
    ctx = ctx or _noop_ctx
    mode = "AI sampling" if use_sampling else "template"
    await ctx.info(f"Analyzing event {event_id} using {mode} mode")
    await ctx.report_progress(0, 4)

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute(
            "SELECT * FROM k8s_events WHERE event_id = %s", (event_id,)
        )
        row = cursor.fetchone()
        if not row:
            await ctx.warning(f"Event '{event_id}' not found.")
            return f"Event '{event_id}' not found."

        event = dict(row)
        reason = event.get("reason", "")
        kind = event.get("kind", "Pod")
        name = event.get("name", "unknown")
        namespace = event.get("namespace", "default")
        message = event.get("message", "")

        await ctx.report_progress(1, 4)

        if use_sampling:
            # --- Sampling path: ask Claude via the MCP client ---
            await ctx.info(f"Requesting AI analysis via sampling for {kind} {namespace}/{name}")
            prompt = (
                f"You are a Kubernetes expert. Analyze this event and provide:\n"
                f"1. Root cause analysis\n"
                f"2. Diagnostic commands to run\n"
                f"3. Suggested fixes\n\n"
                f"Event details:\n"
                f"  Kind: {kind}\n"
                f"  Name: {namespace}/{name}\n"
                f"  Reason: {reason}\n"
                f"  Severity: {event.get('severity', 'unknown')}\n"
                f"  Message: {message}\n"
                f"  Raw payload: {event.get('raw_payload', 'N/A')}\n"
            )
            try:
                result = await mcp.sample(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt="You are a senior Kubernetes SRE. Provide concise, actionable analysis.",
                    max_tokens=1024,
                )
                full_analysis = (
                    f"# AI Analysis for {kind} `{namespace}/{name}`\n\n"
                    f"**Event ID:** {event_id}\n"
                    f"**Reason:** {reason}\n"
                    f"**Severity:** {event.get('severity', 'unknown')}\n"
                    f"**Message:** {message}\n"
                    f"**Timestamp:** {event.get('created_at', 'unknown')}\n\n"
                    f"{result.text}"
                )
                await ctx.info("AI analysis completed successfully")
            except Exception as e:
                await ctx.warning(f"Sampling failed, falling back to template: {e}")
                full_analysis = _template_analysis(event_id, event)
        else:
            # --- Template path: use built-in templates ---
            await ctx.info(f"Using template analysis for reason: {reason}")
            full_analysis = _template_analysis(event_id, event)

        await ctx.report_progress(2, 4)

        # Mark as analyzed
        await ctx.info(f"Updating event {event_id} status to 'analyzed'")
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE k8s_events SET status = 'analyzed', analysis = %s, updated_at = %s WHERE event_id = %s",
            (full_analysis, now, event_id),
        )
        conn.commit()
        await ctx.report_progress(3, 4)
    finally:
        conn.close()

    await ctx.info(f"Analysis complete for event {event_id}")
    await ctx.report_progress(4, 4)
    return full_analysis


def _template_analysis(event_id: str, event: dict) -> str:
    """Generate analysis using built-in templates."""
    reason = event.get("reason", "")
    kind = event.get("kind", "Pod")
    name = event.get("name", "unknown")
    namespace = event.get("namespace", "default")
    message = event.get("message", "")

    template = ANALYSIS_TEMPLATES.get(reason, DEFAULT_ANALYSIS)
    analysis = template.format(
        namespace=namespace,
        name=name,
        kind=kind,
        kind_lower=kind.lower() if kind else "resource",
    )

    return (
        f"# Analysis for {kind} `{namespace}/{name}`\n\n"
        f"**Event ID:** {event_id}\n"
        f"**Reason:** {reason}\n"
        f"**Severity:** {event.get('severity', 'unknown')}\n"
        f"**Message:** {message}\n"
        f"**Timestamp:** {event.get('created_at', 'unknown')}\n\n"
        f"{analysis}"
    )


# ---------------------------------------------------------------------------
# Tool: get_cluster_info
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_cluster_info(command: str, ctx: Context = None) -> str:
    """
    Run a READ-ONLY kubectl command to inspect the cluster.
    Only 'get', 'describe', 'logs', 'top', and 'version' subcommands are allowed.

    Args:
        command: The kubectl command (e.g. "kubectl get pods -n default")
    """
    ctx = ctx or _noop_ctx
    await ctx.info(f"Running cluster command: {command}")
    await ctx.report_progress(0, 2)

    allowed_subcommands = {"get", "describe", "logs", "top", "version", "events"}
    parts = command.strip().split()

    if not parts or parts[0] != "kubectl":
        await ctx.error("Command must start with 'kubectl'")
        return "Error: command must start with 'kubectl'."

    subcommand = parts[1] if len(parts) > 1 else ""
    if subcommand not in allowed_subcommands:
        await ctx.error(f"Subcommand '{subcommand}' is not allowed")
        return (
            f"Error: subcommand '{subcommand}' is not allowed. "
            f"Allowed: {', '.join(sorted(allowed_subcommands))}"
        )

    # Block any write flags that could sneak in
    dangerous = {"--force", "delete", "apply", "patch", "edit", "create", "replace"}
    if dangerous & set(parts):
        await ctx.error("Write/destructive operations blocked")
        return "Error: write/destructive operations are not allowed via this tool."

    await ctx.report_progress(1, 2)

    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout or ""
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        await ctx.info(f"Command completed (exit code: {result.returncode})")
        await ctx.report_progress(2, 2)
        return output if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        await ctx.error("Command timed out after 30 seconds")
        return "Error: command timed out after 30 seconds."
    except FileNotFoundError:
        await ctx.error("kubectl not found in PATH")
        return "Error: kubectl not found. Ensure it is installed and in PATH."
    except Exception as e:
        await ctx.error(f"Command execution error: {e}")
        return f"Error executing command: {e}"


# ---------------------------------------------------------------------------
# Tool: apply_fix
# ---------------------------------------------------------------------------
@mcp.tool()
async def apply_fix(command: str, dry_run: bool = True, ctx: Context = None) -> str:
    """
    Apply a kubectl fix command. Runs in --dry-run=client mode by default.
    Set dry_run=False to apply for real (use with caution).

    Args:
        command:  The kubectl command to run (e.g. "kubectl scale deploy/myapp --replicas=3 -n default")
        dry_run:  If True (default), appends --dry-run=client. Set False to apply.
    """
    ctx = ctx or _noop_ctx
    mode = "DRY-RUN" if dry_run else "LIVE"
    await ctx.info(f"[{mode}] Preparing fix command: {command}")
    await ctx.report_progress(0, 3)

    parts = command.strip().split()

    if not parts or parts[0] != "kubectl":
        await ctx.error("Command must start with 'kubectl'")
        return "Error: command must start with 'kubectl'."

    # Block truly destructive commands
    blocked = {"delete namespace", "delete ns", "drain", "cordon", "taint"}
    cmd_str = " ".join(parts).lower()
    for b in blocked:
        if b in cmd_str:
            await ctx.error(f"Blocked destructive command: '{b}'")
            return f"Error: '{b}' is blocked for safety. Perform this manually."

    if dry_run and "--dry-run" not in cmd_str:
        parts.append("--dry-run=client")

    logger.info("[%s] Running: %s", mode, " ".join(parts))
    await ctx.report_progress(1, 3)

    if not dry_run:
        await ctx.warning(f"Executing LIVE command: {' '.join(parts)}")

    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = f"[{mode}] Command: {' '.join(parts)}\n\n"
        output += result.stdout or ""
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
            await ctx.error(f"Command exited with code {result.returncode}")
        else:
            await ctx.info(f"[{mode}] Command completed successfully")
        await ctx.report_progress(3, 3)
        return output
    except subprocess.TimeoutExpired:
        await ctx.error("Command timed out after 30 seconds")
        return "Error: command timed out after 30 seconds."
    except FileNotFoundError:
        await ctx.error("kubectl not found in PATH")
        return "Error: kubectl not found."
    except Exception as e:
        await ctx.error(f"Command execution error: {e}")
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool: mark_resolved
# ---------------------------------------------------------------------------
@mcp.tool()
async def mark_resolved(event_id: str, resolution_note: str = "", ctx: Context = None) -> str:
    """
    Mark an event as resolved after a fix has been applied.

    Args:
        event_id:        The event ID to mark resolved
        resolution_note: Optional note describing what was done
    """
    ctx = ctx or _noop_ctx
    await ctx.info(f"Marking event {event_id} as resolved")
    await ctx.report_progress(0, 2)

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE k8s_events SET status = 'resolved', analysis = CONCAT(COALESCE(analysis, ''), %s), updated_at = %s WHERE event_id = %s",
            (f"\n\n---\n**Resolved:** {resolution_note}" if resolution_note else "", now, event_id),
        )
        conn.commit()
        await ctx.report_progress(1, 2)
        if cursor.rowcount == 0:
            await ctx.warning(f"Event '{event_id}' not found.")
            return f"Event '{event_id}' not found."
    finally:
        conn.close()

    await ctx.info(f"Event {event_id} resolved successfully")
    await ctx.report_progress(2, 2)
    return f"Event {event_id} marked as resolved."


# ---------------------------------------------------------------------------
# Tool: get_event_summary
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_event_summary(ctx: Context = None) -> str:
    """
    Get a summary dashboard of all events grouped by severity and status.
    Useful for a quick overview of cluster health.
    """
    ctx = ctx or _noop_ctx
    await ctx.info("Generating cluster event summary")
    await ctx.report_progress(0, 4)

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute(
            "SELECT severity, COUNT(*) as cnt FROM k8s_events GROUP BY severity"
        )
        severity_rows = cursor.fetchall()
        await ctx.report_progress(1, 4)

        cursor.execute(
            "SELECT status, COUNT(*) as cnt FROM k8s_events GROUP BY status"
        )
        status_rows = cursor.fetchall()
        await ctx.report_progress(2, 4)

        cursor.execute(
            "SELECT event_id, severity, namespace, name, reason, message, created_at "
            "FROM k8s_events ORDER BY created_at DESC LIMIT 5"
        )
        recent = cursor.fetchall()
        await ctx.report_progress(3, 4)
    finally:
        conn.close()

    lines = ["# Kubernetes Cluster Event Summary\n"]

    lines.append("## By Severity")
    for r in severity_rows:
        lines.append(f"  - **{r['severity'].upper()}**: {r['cnt']}")

    lines.append("\n## By Status")
    for r in status_rows:
        lines.append(f"  - **{r['status']}**: {r['cnt']}")

    lines.append("\n## Latest 5 Events")
    for r in recent:
        lines.append(
            f"  - `{r['event_id']}` [{r['severity']}] "
            f"{r['namespace']}/{r['name']} – {r['reason']}: {(r['message'] or '')[:80]}"
        )

    await ctx.info(f"Summary complete: {len(severity_rows)} severity groups, {len(recent)} recent events")
    await ctx.report_progress(4, 4)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: trace_resource_usage
# ---------------------------------------------------------------------------
@mcp.tool()
async def trace_resource_usage(pod: str, namespace: str = "default", ctx: Context = None) -> str:
    """
    Analyze why a specific pod has high resource usage.

    Args:
        pod:       The pod name to trace
        namespace: The namespace (default: 'default')
    """
    ctx = ctx or _noop_ctx
    await ctx.info(f"Tracing resource usage for pod {namespace}/{pod}")
    await ctx.report_progress(0, 4)
    sections = []

    await ctx.debug("Fetching pod description")
    try:
        r = subprocess.run(
            ["kubectl", "describe", "pod", pod, "-n", namespace],
            capture_output=True, text=True, timeout=15,
        )
        sections.append(f"## Pod Description\n{(r.stdout if r.returncode == 0 else r.stderr)[:3000]}")
    except Exception as e:
        sections.append(f"## Pod Description\nError: {e}")
    await ctx.report_progress(1, 4)

    await ctx.debug("Fetching current resource usage")
    try:
        r = subprocess.run(
            ["kubectl", "top", "pod", pod, "-n", namespace, "--no-headers"],
            capture_output=True, text=True, timeout=10,
        )
        sections.append(f"## Current Usage\n{r.stdout if r.returncode == 0 else 'metrics-server unavailable'}")
    except Exception:
        sections.append("## Current Usage\nmetrics-server unavailable")
    await ctx.report_progress(2, 4)

    await ctx.debug("Fetching recent events")
    try:
        r = subprocess.run(
            ["kubectl", "get", "events", "-n", namespace,
             "--field-selector", f"involvedObject.name={pod}", "--sort-by=.lastTimestamp"],
            capture_output=True, text=True, timeout=10,
        )
        sections.append(f"## Recent Events\n{(r.stdout or '(no events)')[:1500]}")
    except Exception:
        sections.append("## Recent Events\n(could not fetch events)")
    await ctx.report_progress(3, 4)

    await ctx.debug("Fetching recent logs")
    try:
        r = subprocess.run(
            ["kubectl", "logs", pod, "-n", namespace, "--tail=30"],
            capture_output=True, text=True, timeout=10,
        )
        sections.append(f"## Recent Logs\n{(r.stdout or '(no logs)')[:2000]}")
    except Exception:
        sections.append("## Recent Logs\n(could not fetch logs)")

    await ctx.info(f"Resource trace complete for {namespace}/{pod}")
    await ctx.report_progress(4, 4)
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Tool: get_jvm_details
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_jvm_details(namespace: str = "default", ctx: Context = None) -> str:
    """
    Get JVM configuration details for Java pods in a namespace.

    Args:
        namespace: The namespace to scan (default: 'default')
    """
    ctx = ctx or _noop_ctx
    import re as _re

    await ctx.info(f"Scanning JVM details in namespace: {namespace}")
    await ctx.report_progress(0, 3)

    try:
        r = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            await ctx.error(f"Failed to list pods: {r.stderr}")
            return f"Error: {r.stderr}"
        data = json.loads(r.stdout)
    except Exception as e:
        await ctx.error(f"Error fetching pods: {e}")
        return f"Error: {e}"

    await ctx.report_progress(1, 3)

    jvm_env_keys = {"JAVA_OPTS", "JAVA_TOOL_OPTIONS", "JVM_OPTS", "_JAVA_OPTIONS"}
    lines = ["# JVM Details Report\n"]
    found = 0
    items = data.get("items", [])

    for item in items:
        pod_name = item["metadata"]["name"]
        if item.get("status", {}).get("phase") != "Running":
            continue

        for container in item.get("spec", {}).get("containers", []):
            env_list = container.get("env", [])
            jvm_vars = {e["name"]: e.get("value", "") for e in env_list if e.get("name") in jvm_env_keys}
            if not jvm_vars:
                continue
            found += 1
            await ctx.debug(f"Found JVM config in {pod_name}/{container['name']}")

            lines.append(f"## Pod: {pod_name} / Container: {container['name']}")
            lines.append("**Expected (from env vars):**")
            for k, v in jvm_vars.items():
                lines.append(f"  {k}={v}")

            actual = "(could not retrieve)"
            try:
                ar = subprocess.run(
                    ["kubectl", "exec", pod_name, "-n", namespace,
                     "-c", container["name"], "--", "jcmd", "1", "VM.flags"],
                    capture_output=True, text=True, timeout=10,
                )
                if ar.returncode == 0:
                    actual = ar.stdout.strip()
            except Exception:
                pass

            lines.append(f"**Actual (runtime):**\n{actual[:500]}\n")

    await ctx.report_progress(2, 3)

    if found == 0:
        await ctx.info("No Java pods with JVM environment variables found")
        lines.append("No Java pods with JVM environment variables found in this namespace.")
    else:
        await ctx.info(f"Found JVM config in {found} container(s)")

    await ctx.report_progress(3, 3)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: get_network_status
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_network_status(namespace: str = "all", test_latency: bool = False, ctx: Context = None) -> str:
    """
    Get service network status including endpoints and optionally test latency.

    Args:
        namespace:    Namespace to check, or 'all' (default: 'all')
        test_latency: If True, actively measure latency (slower)
    """
    ctx = ctx or _noop_ctx
    await ctx.info(f"Checking network status (namespace={namespace})")
    await ctx.report_progress(0, 4)
    lines = ["# Network Status Report\n"]

    await ctx.debug("Fetching services")
    svc_args = ["kubectl", "get", "services", "-o", "wide"]
    if namespace == "all":
        svc_args.append("--all-namespaces")
    else:
        svc_args.extend(["-n", namespace])
    try:
        r = subprocess.run(svc_args, capture_output=True, text=True, timeout=10)
        lines.append(f"## Services\n{r.stdout}")
    except Exception as e:
        lines.append(f"## Services\nError: {e}")
    await ctx.report_progress(1, 4)

    await ctx.debug("Fetching endpoints")
    ep_args = ["kubectl", "get", "endpoints"]
    if namespace == "all":
        ep_args.append("--all-namespaces")
    else:
        ep_args.extend(["-n", namespace])
    try:
        r = subprocess.run(ep_args, capture_output=True, text=True, timeout=10)
        lines.append(f"## Endpoints\n{r.stdout}")
    except Exception as e:
        lines.append(f"## Endpoints\nError: {e}")
    await ctx.report_progress(2, 4)

    await ctx.debug("Checking for NetworkNotReady events")
    try:
        r = subprocess.run(
            ["kubectl", "get", "events", "--all-namespaces",
             "--field-selector", "reason=NetworkNotReady"],
            capture_output=True, text=True, timeout=10,
        )
        net = r.stdout.strip()
        lines.append(f"## Network Issues\n{net if net else 'No NetworkNotReady events found.'}")
    except Exception:
        lines.append("## Network Issues\n(could not check)")
    await ctx.report_progress(3, 4)

    await ctx.debug("Fetching network policies")
    try:
        np_args = ["kubectl", "get", "networkpolicies"]
        if namespace == "all":
            np_args.append("--all-namespaces")
        else:
            np_args.extend(["-n", namespace])
        r = subprocess.run(np_args, capture_output=True, text=True, timeout=10)
        lines.append(f"## Network Policies\n{r.stdout or '(none found)'}")
    except Exception:
        pass

    await ctx.info("Network status check complete")
    await ctx.report_progress(4, 4)
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Run:  python mcp_server.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Starting MCP K8s Event Analyzer server (stdio)…")
    mcp.run(transport="stdio")
