import json
import logging
import re
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_auth

logger = logging.getLogger("cluster-api")

router = APIRouter(prefix="/api/cluster", tags=["cluster"], dependencies=[Depends(require_auth)])


def _run_kubectl(args: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["kubectl"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=502,
                detail=f"kubectl error: {result.stderr.strip()}",
            )
        return result.stdout
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="kubectl timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="kubectl not found")


# ── Resource parsing helpers ──


def _parse_cpu(value: str) -> int:
    """Parse K8s CPU string to millicores. '500m'->500, '1'->1000, '0.5'->500."""
    if not value or value == "0":
        return 0
    value = value.strip()
    if value.endswith("m"):
        return int(value[:-1])
    try:
        return int(float(value) * 1000)
    except ValueError:
        return 0


def _parse_memory(value: str) -> int:
    """Parse K8s memory string to bytes. '128Mi'->134217728, '1Gi'->1073741824."""
    if not value or value == "0":
        return 0
    value = value.strip()
    multipliers = {
        "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4,
        "K": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4,
    }
    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            try:
                return int(float(value[: -len(suffix)]) * mult)
            except ValueError:
                return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _format_cpu(millicores: int) -> str:
    if millicores == 0:
        return "N/A"
    if millicores >= 1000 and millicores % 1000 == 0:
        return str(millicores // 1000)
    return f"{millicores}m"


def _format_memory(bytes_val: int) -> str:
    if bytes_val == 0:
        return "N/A"
    if bytes_val >= 1024**3:
        return f"{bytes_val / (1024**3):.1f}Gi"
    return f"{bytes_val / (1024**2):.0f}Mi"


def _parse_jvm_flags(text: str) -> dict[str, str]:
    """Extract known JVM flags from a text string (env vars or jcmd output)."""
    flags: dict[str, str] = {}
    for m in re.finditer(r"(-Xmx\S+)", text):
        flags["Xmx"] = m.group(1)
    for m in re.finditer(r"(-Xms\S+)", text):
        flags["Xms"] = m.group(1)
    for m in re.finditer(r"(-XX:MaxMetaspaceSize=\S+)", text):
        flags["MaxMetaspaceSize"] = m.group(1)
    for m in re.finditer(r"(-XX:\+Use(\w+)GC)", text):
        flags["GC"] = m.group(1)
    for m in re.finditer(r"(-XX:MaxRAMPercentage=\S+)", text):
        flags["MaxRAMPercentage"] = m.group(1)
    for m in re.finditer(r"-XX:MaxHeapSize=(\d+)", text):
        flags.setdefault("Xmx", f"-Xmx{int(m.group(1)) // (1024 * 1024)}m")
    for m in re.finditer(r"-XX:InitialHeapSize=(\d+)", text):
        flags.setdefault("Xms", f"-Xms{int(m.group(1)) // (1024 * 1024)}m")
    return flags


@router.get("/nodes")
async def get_nodes():
    output = _run_kubectl(["get", "nodes", "-o", "json"])
    data = json.loads(output)
    nodes = []
    for item in data.get("items", []):
        meta = item.get("metadata", {})
        status = item.get("status", {})
        conditions = {c["type"]: c["status"] for c in status.get("conditions", [])}
        info = status.get("nodeInfo", {})
        nodes.append({
            "name": meta.get("name"),
            "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
            "roles": ",".join(
                k.replace("node-role.kubernetes.io/", "")
                for k in meta.get("labels", {})
                if k.startswith("node-role.kubernetes.io/")
            ) or "worker",
            "version": info.get("kubeletVersion", ""),
            "os": info.get("osImage", ""),
            "kernel": info.get("kernelVersion", ""),
            "container_runtime": info.get("containerRuntimeVersion", ""),
            "created": meta.get("creationTimestamp", ""),
        })
    return {"nodes": nodes}


@router.get("/namespaces")
async def get_namespaces():
    output = _run_kubectl(["get", "namespaces", "-o", "json"])
    data = json.loads(output)
    namespaces = [
        {
            "name": item["metadata"]["name"],
            "status": item.get("status", {}).get("phase", ""),
            "created": item["metadata"].get("creationTimestamp", ""),
        }
        for item in data.get("items", [])
    ]
    return {"namespaces": namespaces}


@router.get("/pods")
async def get_pods(namespace: str = Query("default")):
    output = _run_kubectl(["get", "pods", "-n", namespace, "-o", "json"])
    data = json.loads(output)
    pods = []
    for item in data.get("items", []):
        meta = item.get("metadata", {})
        status = item.get("status", {})
        spec = item.get("spec", {})
        container_statuses = status.get("containerStatuses", [])
        init_statuses = status.get("initContainerStatuses", [])
        restarts = sum(c.get("restartCount", 0) for c in container_statuses)
        ready = sum(1 for c in container_statuses if c.get("ready"))
        total = len(container_statuses)
        containers = [c["name"] for c in spec.get("containers", [])]
        init_containers = [c["name"] for c in spec.get("initContainers", [])]
        pods.append({
            "name": meta.get("name"),
            "namespace": namespace,
            "status": status.get("phase", "Unknown"),
            "ready": f"{ready}/{total}",
            "restarts": restarts,
            "node": spec.get("nodeName", ""),
            "created": meta.get("creationTimestamp", ""),
            "containers": containers,
            "initContainers": init_containers,
        })
    return {"pods": pods}


@router.get("/logs")
async def get_logs(
    namespace: str = Query("default"),
    pod: str = Query(...),
    container: str = Query(""),
    lines: int = Query(100, le=5000),
    previous: bool = Query(False),
    since: str = Query(""),
):
    """
    Fetch pod logs with advanced options.

    - container: specific container name (required for multi-container pods)
    - lines: number of tail lines (max 5000)
    - previous: if True, fetch logs from the previous terminated container
    - since: duration string like "1h", "30m", "2h30m" to get logs from that time ago
    """
    args = ["logs", "-n", namespace, pod, f"--tail={lines}"]
    if container:
        args.extend(["-c", container])
    if previous:
        args.append("--previous")
    if since:
        args.extend([f"--since={since}"])
    output = _run_kubectl(args, timeout=30)
    return {"logs": output, "pod": pod, "namespace": namespace, "container": container, "previous": previous}


# ── Resource Allocation ──


@router.get("/resources")
async def get_resources(namespace: str = Query("all")):
    """Per-pod resource allocation (requests/limits) vs actual usage."""
    # 1. Actual usage from kubectl top
    top_args = ["top", "pods", "--no-headers"]
    if namespace == "all":
        top_args.append("--all-namespaces")
    else:
        top_args.extend(["-n", namespace])

    try:
        top_output = _run_kubectl(top_args, timeout=15)
    except HTTPException:
        top_output = ""

    usage_map: dict[tuple[str, str], dict] = {}
    for line in top_output.strip().splitlines():
        parts = line.split()
        if not parts:
            continue
        if namespace == "all" and len(parts) >= 4:
            ns, name, cpu, mem = parts[0], parts[1], parts[2], parts[3]
        elif len(parts) >= 3:
            ns, name, cpu, mem = namespace, parts[0], parts[1], parts[2]
        else:
            continue
        usage_map[(ns, name)] = {"cpu_usage": cpu, "memory_usage": mem}

    # 2. Resource requests/limits from pod specs
    spec_args = ["get", "pods", "-o", "json"]
    if namespace == "all":
        spec_args.append("--all-namespaces")
    else:
        spec_args.extend(["-n", namespace])

    spec_output = _run_kubectl(spec_args, timeout=60)
    data = json.loads(spec_output)

    pods = []
    for item in data.get("items", []):
        meta = item.get("metadata", {})
        spec = item.get("spec", {})
        pod_ns = meta.get("namespace", "default")
        pod_name = meta.get("name", "")
        status_phase = item.get("status", {}).get("phase", "Unknown")

        total_cpu_req = total_cpu_lim = total_mem_req = total_mem_lim = 0
        for container in spec.get("containers", []):
            resources = container.get("resources", {})
            requests = resources.get("requests", {})
            limits = resources.get("limits", {})
            total_cpu_req += _parse_cpu(requests.get("cpu", "0"))
            total_cpu_lim += _parse_cpu(limits.get("cpu", "0"))
            total_mem_req += _parse_memory(requests.get("memory", "0"))
            total_mem_lim += _parse_memory(limits.get("memory", "0"))

        usage = usage_map.get((pod_ns, pod_name), {})
        cpu_usage_m = _parse_cpu(usage.get("cpu_usage", "0"))
        mem_usage_bytes = _parse_memory(usage.get("memory_usage", "0"))

        cpu_denom = total_cpu_lim if total_cpu_lim > 0 else total_cpu_req
        mem_denom = total_mem_lim if total_mem_lim > 0 else total_mem_req
        cpu_pct = round((cpu_usage_m / cpu_denom) * 100, 1) if cpu_denom > 0 else 0.0
        mem_pct = round((mem_usage_bytes / mem_denom) * 100, 1) if mem_denom > 0 else 0.0

        pods.append({
            "name": pod_name,
            "namespace": pod_ns,
            "status": status_phase,
            "cpu_request": _format_cpu(total_cpu_req),
            "cpu_limit": _format_cpu(total_cpu_lim),
            "cpu_usage": usage.get("cpu_usage", "N/A"),
            "cpu_percent": cpu_pct,
            "memory_request": _format_memory(total_mem_req),
            "memory_limit": _format_memory(total_mem_lim),
            "memory_usage": usage.get("memory_usage", "N/A"),
            "memory_percent": mem_pct,
        })

    return {"pods": pods, "metrics_available": bool(top_output.strip())}


# ── Resource Trace ──


@router.get("/resources/trace")
async def trace_resource(
    pod: str = Query(...),
    namespace: str = Query("default"),
):
    """Trace why a pod's resource usage is high using LLM analysis."""
    sections: dict[str, str] = {}
    try:
        sections["describe"] = _run_kubectl(["describe", "pod", pod, "-n", namespace], timeout=15)
    except HTTPException:
        sections["describe"] = "(failed to describe pod)"
    try:
        sections["events"] = _run_kubectl([
            "get", "events", "-n", namespace,
            "--field-selector", f"involvedObject.name={pod}",
            "--sort-by=.lastTimestamp",
        ], timeout=10)
    except HTTPException:
        sections["events"] = "(no events found)"
    try:
        sections["logs"] = _run_kubectl(["logs", pod, "-n", namespace, "--tail=50"], timeout=10)
    except HTTPException:
        sections["logs"] = "(failed to get logs)"
    try:
        sections["top"] = _run_kubectl(["top", "pod", pod, "-n", namespace, "--no-headers"], timeout=10)
    except HTTPException:
        sections["top"] = "(metrics unavailable)"

    from .llm_client import get_openai_client, get_model
    prompt = f"""Analyze why pod '{pod}' in namespace '{namespace}' may be consuming high resources.

## Pod Description
{sections['describe'][:3000]}

## Recent Events
{sections['events'][:1500]}

## Recent Logs (last 50 lines)
{sections['logs'][:2000]}

## Current Resource Usage
{sections['top']}

Provide:
1. Root cause analysis
2. Specific evidence from the data
3. Recommended remediation steps
4. Risk assessment (Critical / Warning / Informational)

Format in clear markdown."""

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=get_model(),
            messages=[
                {"role": "system", "content": "You are a Kubernetes resource analysis expert."},
                {"role": "user", "content": prompt},
            ],
        )
        analysis = response.choices[0].message.content or "Analysis unavailable"
    except Exception as e:
        analysis = f"LLM analysis failed: {e}"

    return {
        "pod": pod,
        "namespace": namespace,
        "analysis": analysis,
        "raw": {
            "describe_snippet": sections["describe"][:500],
            "top": sections["top"],
            "event_count": len(sections["events"].strip().splitlines()),
        },
    }


# ── JVM Details ──


@router.get("/jvm")
async def get_jvm_details(namespace: str = Query("default")):
    """Show JVM expected (env vars) vs obtained (runtime) for Java pods."""
    output = _run_kubectl(["get", "pods", "-n", namespace, "-o", "json"])
    data = json.loads(output)

    jvm_env_keys = {"JAVA_OPTS", "JAVA_TOOL_OPTIONS", "JVM_OPTS", "_JAVA_OPTIONS", "JAVA_OPTIONS"}
    jvm_pods = []

    for item in data.get("items", []):
        meta = item.get("metadata", {})
        pod_name = meta.get("name", "")
        phase = item.get("status", {}).get("phase", "Unknown")
        if phase != "Running":
            continue

        for container in item.get("spec", {}).get("containers", []):
            container_name = container.get("name", "")
            env_list = container.get("env", [])
            jvm_vars = {e["name"]: e.get("value", "") for e in env_list if e.get("name") in jvm_env_keys}
            if not jvm_vars:
                continue

            expected = _parse_jvm_flags(" ".join(jvm_vars.values()))

            # Try jcmd for actual flags
            actual_raw = ""
            try:
                actual_raw = _run_kubectl([
                    "exec", pod_name, "-n", namespace, "-c", container_name,
                    "--", "jcmd", "1", "VM.flags",
                ], timeout=10)
            except HTTPException:
                try:
                    cmdline = _run_kubectl([
                        "exec", pod_name, "-n", namespace, "-c", container_name,
                        "--", "cat", "/proc/1/cmdline",
                    ], timeout=10)
                    actual_raw = cmdline.replace("\x00", " ")
                except HTTPException:
                    actual_raw = "(could not retrieve actual JVM flags)"

            actual = _parse_jvm_flags(actual_raw)
            mismatches = []
            for key in set(list(expected.keys()) + list(actual.keys())):
                exp_val = expected.get(key, "not set")
                act_val = actual.get(key, "not set")
                if exp_val != act_val and exp_val != "not set" and act_val != "not set":
                    mismatches.append({"flag": key, "expected": exp_val, "actual": act_val})

            jvm_pods.append({
                "pod": pod_name,
                "container": container_name,
                "namespace": namespace,
                "env_vars": jvm_vars,
                "expected": expected,
                "actual": actual,
                "actual_raw": actual_raw[:500],
                "mismatches": mismatches,
                "has_mismatches": len(mismatches) > 0,
            })

    return {"jvm_pods": jvm_pods, "namespace": namespace}


# ── Network Latency ──


def _find_source_pod(namespace: str) -> dict | None:
    """Find a running pod to use as a curl source."""
    try:
        output = _run_kubectl([
            "get", "pods", "-n", namespace, "-o", "json",
            "--field-selector=status.phase=Running",
        ])
        items = json.loads(output).get("items", [])
        if items:
            pod = items[0]
            return {
                "name": pod["metadata"]["name"],
                "namespace": namespace,
                "ip": pod.get("status", {}).get("podIP", ""),
            }
    except (HTTPException, json.JSONDecodeError):
        pass
    return None


@router.get("/network")
async def get_network_info(
    namespace: str = Query("all"),
    test_latency: bool = Query(False),
    source_pod: str = Query(""),
    source_ns: str = Query(""),
    target_pod: str = Query(""),
):
    """Service network info: endpoints, latency, network issues."""
    # Services
    svc_args = ["get", "services", "-o", "json"]
    if namespace == "all":
        svc_args.append("--all-namespaces")
    else:
        svc_args.extend(["-n", namespace])
    svc_data = json.loads(_run_kubectl(svc_args, timeout=15))

    # Endpoints
    ep_args = ["get", "endpoints", "-o", "json"]
    if namespace == "all":
        ep_args.append("--all-namespaces")
    else:
        ep_args.extend(["-n", namespace])
    ep_data = json.loads(_run_kubectl(ep_args, timeout=15))

    # Network events
    network_issues = []
    try:
        net_events = json.loads(_run_kubectl([
            "get", "events", "--all-namespaces",
            "--field-selector", "reason=NetworkNotReady", "-o", "json",
        ], timeout=10))
        network_issues = [
            {
                "namespace": e["metadata"].get("namespace", ""),
                "name": e.get("involvedObject", {}).get("name", ""),
                "message": e.get("message", ""),
                "timestamp": e["metadata"].get("creationTimestamp", ""),
            }
            for e in net_events.get("items", [])
        ]
    except (HTTPException, json.JSONDecodeError):
        pass

    # Network policies
    network_policies = []
    try:
        np_args = ["get", "networkpolicies", "-o", "json"]
        if namespace == "all":
            np_args.append("--all-namespaces")
        else:
            np_args.extend(["-n", namespace])
        np_data = json.loads(_run_kubectl(np_args, timeout=10))
        network_policies = [
            {
                "name": p["metadata"]["name"],
                "namespace": p["metadata"].get("namespace", ""),
                "pod_selector": p.get("spec", {}).get("podSelector", {}),
            }
            for p in np_data.get("items", [])
        ]
    except (HTTPException, json.JSONDecodeError):
        pass

    # Build endpoint map
    ep_map: dict[str, list[str]] = {}
    for item in ep_data.get("items", []):
        key = f"{item['metadata'].get('namespace', '')}/{item['metadata']['name']}"
        addresses = []
        for subset in item.get("subsets", []):
            for addr in subset.get("addresses", []):
                addresses.append(addr.get("ip", ""))
        ep_map[key] = addresses

    # Build service list
    services = []
    for item in svc_data.get("items", []):
        meta = item.get("metadata", {})
        spec = item.get("spec", {})
        svc_ns = meta.get("namespace", "")
        svc_name = meta.get("name", "")
        endpoints = ep_map.get(f"{svc_ns}/{svc_name}", [])
        services.append({
            "name": svc_name,
            "namespace": svc_ns,
            "type": spec.get("type", "ClusterIP"),
            "clusterIP": spec.get("clusterIP", ""),
            "ports": [
                {"port": p.get("port"), "protocol": p.get("protocol", "TCP"), "targetPort": p.get("targetPort")}
                for p in spec.get("ports", [])
            ],
            "endpoints": endpoints,
            "endpoint_count": len(endpoints),
            "has_endpoints": len(endpoints) > 0,
        })

    # Optional latency testing
    latency_results = []
    if test_latency:
        # Use user-specified source pod or auto-pick
        if source_pod and source_ns:
            try:
                pod_json = json.loads(_run_kubectl(["get", "pod", source_pod, "-n", source_ns, "-o", "json"], timeout=10))
                source = {"name": source_pod, "namespace": source_ns, "ip": pod_json.get("status", {}).get("podIP", "")}
            except (HTTPException, json.JSONDecodeError):
                source = {"name": source_pod, "namespace": source_ns, "ip": ""}
        else:
            source = _find_source_pod(namespace if namespace != "all" else "default")
        if source:
            source_ip = source.get("ip", "")

            # If a specific target pod is specified, test directly to that pod
            if target_pod and namespace != "all":
                target_ns = namespace
                try:
                    tgt_json = json.loads(_run_kubectl(["get", "pod", target_pod, "-n", target_ns, "-o", "json"], timeout=10))
                    tgt_ip = tgt_json.get("status", {}).get("podIP", "")
                    # Find a service port for this pod, or default to common ports
                    tgt_port = 80
                    for svc in services:
                        if tgt_ip and tgt_ip in svc.get("endpoints", []):
                            tgt_port = svc["ports"][0]["port"] if svc["ports"] else 80
                            break
                    target_url = f"http://{tgt_ip}:{tgt_port}/"
                    try:
                        result = _run_kubectl([
                            "exec", source["name"], "-n", source["namespace"],
                            "--", "curl", "-s", "-o", "/dev/null",
                            "-w", "%{time_total}", "--connect-timeout", "3", "--max-time", "5",
                            target_url,
                        ], timeout=10)
                        latency_ms = round(float(result.strip()) * 1000, 2)
                        latency_results.append({
                            "source": f"{source['namespace']}/{source['name']}",
                            "target_service": f"{target_ns}/{target_pod}",
                            "latency_ms": latency_ms,
                            "status": "ok" if latency_ms < 1000 else "slow",
                        })
                    except (HTTPException, ValueError):
                        latency_results.append({
                            "source": f"{source['namespace']}/{source['name']}",
                            "target_service": f"{target_ns}/{target_pod}",
                            "latency_ms": -1,
                            "status": "unreachable",
                        })
                except (HTTPException, json.JSONDecodeError):
                    latency_results.append({
                        "source": f"{source['namespace']}/{source['name']}",
                        "target_service": f"{namespace}/{target_pod}",
                        "latency_ms": -1,
                        "status": "unreachable",
                    })
            else:
                # Test against services
                tested = 0
                for svc in services:
                    if tested >= 10:
                        break
                    if svc["clusterIP"] == "None" or not svc["ports"]:
                        continue
                    # Skip services the source pod belongs to (self-test)
                    if source_ip and source_ip in svc.get("endpoints", []):
                        continue
                    port = svc["ports"][0]["port"]
                    target = f"http://{svc['name']}.{svc['namespace']}.svc.cluster.local:{port}/"
                    try:
                        result = _run_kubectl([
                            "exec", source["name"], "-n", source["namespace"],
                            "--", "curl", "-s", "-o", "/dev/null",
                            "-w", "%{time_total}", "--connect-timeout", "3", "--max-time", "5",
                            target,
                        ], timeout=10)
                        latency_ms = round(float(result.strip()) * 1000, 2)
                        latency_results.append({
                            "source": f"{source['namespace']}/{source['name']}",
                            "target_service": f"{svc['namespace']}/{svc['name']}",
                            "latency_ms": latency_ms,
                            "status": "ok" if latency_ms < 1000 else "slow",
                        })
                    except (HTTPException, ValueError):
                        latency_results.append({
                            "source": f"{source['namespace']}/{source['name']}",
                            "target_service": f"{svc['namespace']}/{svc['name']}",
                            "latency_ms": -1,
                            "status": "unreachable",
                        })
                    tested += 1

    return {
        "services": services,
        "network_issues": network_issues,
        "network_policies": network_policies,
        "latency_results": latency_results,
        "latency_tested": test_latency,
    }
