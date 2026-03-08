const API_BASE =
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:8001`;

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("auth_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface ClusterNode {
  name: string;
  status: string;
  roles: string;
  version: string;
  os: string;
  kernel: string;
  container_runtime: string;
  created: string;
}

export interface Pod {
  name: string;
  namespace: string;
  status: string;
  ready: string;
  restarts: number;
  node: string;
  created: string;
  containers: string[];
  initContainers: string[];
}

export interface Namespace {
  name: string;
  status: string;
  created: string;
}

export async function fetchNodes(): Promise<ClusterNode[]> {
  const res = await fetch(`${API_BASE}/api/cluster/nodes`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Nodes API error: ${res.status}`);
  const data = await res.json();
  return data.nodes;
}

export async function fetchNamespaces(): Promise<Namespace[]> {
  const res = await fetch(`${API_BASE}/api/cluster/namespaces`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Namespaces API error: ${res.status}`);
  const data = await res.json();
  return data.namespaces;
}

export async function fetchPods(namespace: string): Promise<Pod[]> {
  const res = await fetch(`${API_BASE}/api/cluster/pods?namespace=${namespace}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Pods API error: ${res.status}`);
  const data = await res.json();
  return data.pods;
}

export async function fetchLogs(params: {
  namespace: string;
  pod: string;
  container?: string;
  lines?: number;
  previous?: boolean;
  since?: string;
}): Promise<string> {
  const q = new URLSearchParams({
    namespace: params.namespace,
    pod: params.pod,
    lines: String(params.lines ?? 200),
  });
  if (params.container) q.set("container", params.container);
  if (params.previous) q.set("previous", "true");
  if (params.since) q.set("since", params.since);

  const res = await fetch(`${API_BASE}/api/cluster/logs?${q}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Logs API error: ${res.status}`);
  }
  const data = await res.json();
  return data.logs;
}

// ── Resource Allocation ──

export interface PodResource {
  name: string;
  namespace: string;
  status: string;
  cpu_request: string;
  cpu_limit: string;
  cpu_usage: string;
  cpu_percent: number;
  memory_request: string;
  memory_limit: string;
  memory_usage: string;
  memory_percent: number;
}

export interface ResourceResponse {
  pods: PodResource[];
  metrics_available: boolean;
}

export async function fetchResources(namespace: string = "all"): Promise<ResourceResponse> {
  const res = await fetch(`${API_BASE}/api/cluster/resources?namespace=${encodeURIComponent(namespace)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Resources API error: ${res.status}`);
  return res.json();
}

export interface TraceResponse {
  pod: string;
  namespace: string;
  analysis: string;
  raw: { describe_snippet: string; top: string; event_count: number };
}

export async function fetchResourceTrace(pod: string, namespace: string): Promise<TraceResponse> {
  const res = await fetch(
    `${API_BASE}/api/cluster/resources/trace?pod=${encodeURIComponent(pod)}&namespace=${encodeURIComponent(namespace)}`,
    { headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`Trace API error: ${res.status}`);
  return res.json();
}

// ── JVM Details ──

export interface JvmPod {
  pod: string;
  container: string;
  namespace: string;
  env_vars: Record<string, string>;
  expected: Record<string, string>;
  actual: Record<string, string>;
  actual_raw: string;
  mismatches: Array<{ flag: string; expected: string; actual: string }>;
  has_mismatches: boolean;
}

export async function fetchJvmDetails(namespace: string): Promise<{ jvm_pods: JvmPod[]; namespace: string }> {
  const res = await fetch(`${API_BASE}/api/cluster/jvm?namespace=${encodeURIComponent(namespace)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`JVM API error: ${res.status}`);
  return res.json();
}

// ── Network Latency ──

export interface ServiceInfo {
  name: string;
  namespace: string;
  type: string;
  clusterIP: string;
  ports: Array<{ port: number; protocol: string; targetPort: number | string }>;
  endpoints: string[];
  endpoint_count: number;
  has_endpoints: boolean;
}

export interface LatencyResult {
  source: string;
  target_service: string;
  latency_ms: number;
  status: string;
}

export interface NetworkResponse {
  services: ServiceInfo[];
  network_issues: Array<{ namespace: string; name: string; message: string; timestamp: string }>;
  network_policies: Array<{ name: string; namespace: string; pod_selector: Record<string, unknown> }>;
  latency_results: LatencyResult[];
  latency_tested: boolean;
}

export async function fetchNetworkInfo(
  namespace: string = "all",
  testLatency: boolean = false,
  sourcePod?: string,
  sourceNs?: string,
  targetPod?: string,
): Promise<NetworkResponse> {
  const q = new URLSearchParams({ namespace });
  if (testLatency) q.set("test_latency", "true");
  if (sourcePod) q.set("source_pod", sourcePod);
  if (sourceNs) q.set("source_ns", sourceNs);
  if (targetPod) q.set("target_pod", targetPod);
  const res = await fetch(`${API_BASE}/api/cluster/network?${q}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Network API error: ${res.status}`);
  return res.json();
}
