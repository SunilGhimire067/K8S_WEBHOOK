import { useEffect, useState, useRef, useCallback } from "react";
import { fetchResources, fetchResourceTrace, fetchNamespaces } from "../api/clusterApi";
import type { PodResource, ResourceResponse, TraceResponse, Namespace } from "../api/clusterApi";

function BarCell({ percent, label }: { percent: number; label: string }) {
  const color = percent > 90 ? "bar-red" : percent > 70 ? "bar-amber" : "bar-green";
  return (
    <div className="resource-cell">
      <div className="resource-bar">
        <div className={`resource-bar-fill ${color}`} style={{ width: `${Math.min(percent, 100)}%` }} />
      </div>
      <span className="resource-label">{label} ({percent}%)</span>
    </div>
  );
}

export function ResourceAllocationPage() {
  const [data, setData] = useState<ResourceResponse | null>(null);
  const [namespaces, setNamespaces] = useState<Namespace[]>([]);
  const [namespace, setNamespace] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [tracing, setTracing] = useState<string | null>(null);
  const [traceResult, setTraceResult] = useState<TraceResponse | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await fetchResources(namespace);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load resources");
    } finally {
      setLoading(false);
    }
  }, [namespace]);

  useEffect(() => {
    setLoading(true);
    load();
    fetchNamespaces().then(setNamespaces).catch(() => {});
  }, [load]);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(load, 15000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, load]);

  const handleTrace = async (pod: PodResource) => {
    setTracing(pod.name);
    setTraceResult(null);
    try {
      const result = await fetchResourceTrace(pod.name, pod.namespace);
      setTraceResult(result);
    } catch (err) {
      setTraceResult({ pod: pod.name, namespace: pod.namespace, analysis: `Error: ${err}`, raw: { describe_snippet: "", top: "", event_count: 0 } });
    }
  };

  return (
    <div className="resource-page">
      <div className="page-header">
        <h1>Resource Allocation</h1>
        <div className="header-controls">
          <select value={namespace} onChange={(e) => setNamespace(e.target.value)} className="ns-select">
            <option value="all">All Namespaces</option>
            {namespaces.map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
          </select>
          <label className="auto-refresh-toggle">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            Auto-refresh (15s)
          </label>
          <button className="refresh-btn" onClick={() => { setLoading(true); load(); }}>Refresh</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {data && !data.metrics_available && (
        <div className="page-warning">Metrics server not available — usage data will show N/A. Install metrics-server for live data.</div>
      )}

      {loading ? (
        <div className="page-loading">Loading resources...</div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Pod</th>
                <th>Namespace</th>
                <th>Status</th>
                <th>CPU (Usage / Limit)</th>
                <th>Memory (Usage / Limit)</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.pods.map((p) => (
                <tr key={`${p.namespace}/${p.name}`} className={p.cpu_percent > 90 || p.memory_percent > 90 ? "row-critical" : ""}>
                  <td className="pod-name">{p.name}</td>
                  <td className="text-muted">{p.namespace}</td>
                  <td>
                    <span className={`status-dot ${p.status === "Running" ? "green" : "amber"}`} />
                    {p.status}
                  </td>
                  <td>
                    <BarCell percent={p.cpu_percent} label={`${p.cpu_usage} / ${p.cpu_limit}`} />
                  </td>
                  <td>
                    <BarCell percent={p.memory_percent} label={`${p.memory_usage} / ${p.memory_limit}`} />
                  </td>
                  <td>
                    {(p.cpu_percent > 80 || p.memory_percent > 80) && (
                      <button
                        className="trace-btn"
                        onClick={() => handleTrace(p)}
                        disabled={tracing === p.name}
                      >
                        {tracing === p.name ? "Tracing..." : "Trace"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {(!data || data.pods.length === 0) && (
                <tr><td colSpan={6} className="empty-cell">No pods found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {traceResult && (
        <div className="trace-overlay" onClick={() => { setTraceResult(null); setTracing(null); }}>
          <div className="trace-modal" onClick={(e) => e.stopPropagation()}>
            <div className="trace-header">
              <h2>Resource Trace: {traceResult.pod}</h2>
              <button className="close-btn" onClick={() => { setTraceResult(null); setTracing(null); }}>&times;</button>
            </div>
            <div className="trace-body">
              <pre className="trace-analysis">{traceResult.analysis}</pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
