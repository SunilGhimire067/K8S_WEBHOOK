import { useEffect, useState } from "react";
import { fetchJvmDetails, fetchNamespaces } from "../api/clusterApi";
import type { JvmPod, Namespace } from "../api/clusterApi";

export function JvmDetailsPage() {
  const [pods, setPods] = useState<JvmPod[]>([]);
  const [namespaces, setNamespaces] = useState<Namespace[]>([]);
  const [namespace, setNamespace] = useState("default");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchJvmDetails(namespace);
      setPods(data.jvm_pods);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load JVM details");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    fetchNamespaces().then(setNamespaces).catch(() => {});
  }, [namespace]);

  const toggleExpand = (key: string) => {
    setExpanded(expanded === key ? null : key);
  };

  return (
    <div className="jvm-page">
      <div className="page-header">
        <h1>JVM Details</h1>
        <div className="header-controls">
          <select value={namespace} onChange={(e) => setNamespace(e.target.value)} className="ns-select">
            {namespaces.map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
          </select>
          <button className="refresh-btn" onClick={load}>Refresh</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <div className="page-loading">Loading JVM details...</div>
      ) : pods.length === 0 ? (
        <div className="empty-state">
          <p>No Java pods with JVM environment variables found in namespace <strong>{namespace}</strong>.</p>
          <p className="text-muted">Pods must have JAVA_OPTS, JAVA_TOOL_OPTIONS, JVM_OPTS, or _JAVA_OPTIONS env vars.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Pod</th>
                <th>Container</th>
                <th>Expected (Env)</th>
                <th>Actual (Runtime)</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {pods.map((p) => {
                const key = `${p.pod}/${p.container}`;
                const allFlags = [...new Set([...Object.keys(p.expected), ...Object.keys(p.actual)])];
                return (
                  <>
                    <tr
                      key={key}
                      className={`clickable-row ${p.has_mismatches ? "mismatch-row" : ""}`}
                      onClick={() => toggleExpand(key)}
                    >
                      <td className="pod-name">{p.pod}</td>
                      <td>{p.container}</td>
                      <td className="mono-cell">
                        {allFlags.map((f) => (
                          <div key={f}>{f}: {p.expected[f] || "not set"}</div>
                        ))}
                      </td>
                      <td className="mono-cell">
                        {allFlags.map((f) => (
                          <div key={f} className={p.expected[f] !== p.actual[f] && p.expected[f] && p.actual[f] ? "text-warning" : ""}>
                            {f}: {p.actual[f] || "not set"}
                          </div>
                        ))}
                      </td>
                      <td>
                        {p.has_mismatches ? (
                          <span className="status-badge warning">Mismatch</span>
                        ) : (
                          <span className="status-badge ok">Match</span>
                        )}
                      </td>
                    </tr>
                    {expanded === key && (
                      <tr key={`${key}-detail`} className="expanded-row">
                        <td colSpan={5}>
                          <div className="expanded-content">
                            <h4>Environment Variables</h4>
                            <pre>{Object.entries(p.env_vars).map(([k, v]) => `${k}=${v}`).join("\n")}</pre>
                            <h4>Raw JVM Flags</h4>
                            <pre>{p.actual_raw || "(not available)"}</pre>
                            {p.mismatches.length > 0 && (
                              <>
                                <h4>Mismatches</h4>
                                <table className="data-table nested-table">
                                  <thead>
                                    <tr><th>Flag</th><th>Expected</th><th>Actual</th></tr>
                                  </thead>
                                  <tbody>
                                    {p.mismatches.map((m) => (
                                      <tr key={m.flag}>
                                        <td>{m.flag}</td>
                                        <td className="text-ok">{m.expected}</td>
                                        <td className="text-warning">{m.actual}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
