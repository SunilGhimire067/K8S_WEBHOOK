import { useEffect, useState, useCallback } from "react";
import { fetchNamespaces, fetchPods, fetchLogs } from "../api/clusterApi";
import type { Namespace, Pod } from "../api/clusterApi";

const SINCE_OPTIONS = [
  { label: "All available", value: "" },
  { label: "Last 5 minutes", value: "5m" },
  { label: "Last 15 minutes", value: "15m" },
  { label: "Last 30 minutes", value: "30m" },
  { label: "Last 1 hour", value: "1h" },
  { label: "Last 3 hours", value: "3h" },
  { label: "Last 6 hours", value: "6h" },
  { label: "Last 12 hours", value: "12h" },
  { label: "Last 24 hours", value: "24h" },
];

const LINES_OPTIONS = [50, 100, 200, 500, 1000, 2000, 5000];

export function LogsPage() {
  const [namespaces, setNamespaces] = useState<Namespace[]>([]);
  const [pods, setPods] = useState<Pod[]>([]);
  const [selectedNs, setSelectedNs] = useState("");
  const [selectedPod, setSelectedPod] = useState("");
  const [selectedContainer, setSelectedContainer] = useState("");
  const [previous, setPrevious] = useState(false);
  const [since, setSince] = useState("");
  const [lines, setLines] = useState(200);
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const currentPod = pods.find((p) => p.name === selectedPod);
  const containers = currentPod?.containers ?? [];
  const initContainers = currentPod?.initContainers ?? [];
  const allContainers = [...containers, ...initContainers];

  useEffect(() => {
    fetchNamespaces()
      .then(setNamespaces)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selectedNs) {
      setPods([]);
      return;
    }
    setError("");
    fetchPods(selectedNs)
      .then((p) => {
        setPods(p);
        setSelectedPod("");
        setSelectedContainer("");
        setLogs("");
      })
      .catch((e) => setError(e.message));
  }, [selectedNs]);

  useEffect(() => {
    setSelectedContainer("");
    setLogs("");
    setPrevious(false);
  }, [selectedPod]);

  const loadLogs = useCallback(async () => {
    if (!selectedNs || !selectedPod) return;
    setLoading(true);
    setError("");
    try {
      const text = await fetchLogs({
        namespace: selectedNs,
        pod: selectedPod,
        container: selectedContainer || undefined,
        lines,
        previous,
        since: since || undefined,
      });
      setLogs(text);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load logs";
      setError(msg);
      setLogs("");
    } finally {
      setLoading(false);
    }
  }, [selectedNs, selectedPod, selectedContainer, lines, previous, since]);

  useEffect(() => {
    if (selectedPod) loadLogs();
  }, [selectedPod]);

  return (
    <div className="logs-page">
      <div className="page-header">
        <div>
          <h1>Logs</h1>
          <p className="page-subtitle">View container logs from your cluster pods</p>
        </div>
      </div>

      {/* Row 1: Namespace, Pod, Container */}
      <div className="logs-controls">
        <div className="form-field">
          <label>Namespace</label>
          <select
            value={selectedNs}
            onChange={(e) => setSelectedNs(e.target.value)}
          >
            <option value="">Select namespace...</option>
            {namespaces.map((ns) => (
              <option key={ns.name} value={ns.name}>
                {ns.name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label>Pod</label>
          <select
            value={selectedPod}
            onChange={(e) => setSelectedPod(e.target.value)}
            disabled={!selectedNs}
          >
            <option value="">Select pod...</option>
            {pods.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} ({p.status})
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label>Container</label>
          <select
            value={selectedContainer}
            onChange={(e) => setSelectedContainer(e.target.value)}
            disabled={allContainers.length <= 1}
          >
            <option value="">
              {allContainers.length <= 1
                ? allContainers[0] ?? "Default"
                : "Select container..."}
            </option>
            {allContainers.length > 1 &&
              allContainers.map((c) => (
                <option key={c} value={c}>
                  {c}
                  {initContainers.includes(c) ? " (init)" : ""}
                </option>
              ))}
          </select>
        </div>
      </div>

      {/* Row 2: Time range, Lines, Previous, Fetch */}
      <div className="logs-controls">
        <div className="form-field">
          <label>Time Range</label>
          <select value={since} onChange={(e) => setSince(e.target.value)}>
            {SINCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label>Lines</label>
          <select
            value={lines}
            onChange={(e) => setLines(Number(e.target.value))}
          >
            {LINES_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field logs-checkbox-field">
          <label>Previous Container</label>
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={previous}
              onChange={(e) => setPrevious(e.target.checked)}
            />
            <span>Show crashed/restarted logs</span>
          </label>
        </div>

        <button
          className="refresh-btn logs-fetch-btn"
          onClick={loadLogs}
          disabled={!selectedPod || loading}
        >
          {loading ? "Loading..." : "Fetch Logs"}
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="logs-output">
        {loading ? (
          <div className="page-loading">Loading logs...</div>
        ) : logs ? (
          <pre className="log-viewer">{logs}</pre>
        ) : (
          <div className="logs-empty">
            {selectedPod
              ? "No logs found. Try adjusting filters or check if the container has started."
              : "Select a namespace and pod to view logs"}
          </div>
        )}
      </div>
    </div>
  );
}
