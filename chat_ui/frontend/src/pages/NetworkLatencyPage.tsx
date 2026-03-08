import { useEffect, useState } from "react";
import { fetchNetworkInfo, fetchNamespaces, fetchPods } from "../api/clusterApi";
import type { NetworkResponse, LatencyResult, Namespace, Pod } from "../api/clusterApi";

export function NetworkLatencyPage() {
  const [data, setData] = useState<NetworkResponse | null>(null);
  const [namespaces, setNamespaces] = useState<Namespace[]>([]);
  const [sourcePods, setSourcePods] = useState<Pod[]>([]);
  const [targetPods, setTargetPods] = useState<Pod[]>([]);
  const [targetNs, setTargetNs] = useState("all");
  const [sourceNs, setSourceNs] = useState("");
  const [sourcePod, setSourcePod] = useState("");
  const [targetPod, setTargetPod] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [testingLatency, setTestingLatency] = useState(false);
  const [checkResult, setCheckResult] = useState<LatencyResult | null>(null);

  const load = async (testLatency = false) => {
    if (testLatency) {
      setTestingLatency(true);
    } else {
      setLoading(true);
    }
    setError("");
    try {
      const res = await fetchNetworkInfo(
        targetNs,
        testLatency,
        sourcePod || undefined,
        sourceNs || undefined,
        targetPod || undefined,
      );
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load network info");
    } finally {
      setLoading(false);
      setTestingLatency(false);
    }
  };

  // Load namespaces once
  useEffect(() => {
    fetchNamespaces().then(setNamespaces).catch(() => {});
  }, []);

  // Load target services and pods when target namespace changes
  useEffect(() => {
    setTargetPod("");
    load();
    if (targetNs && targetNs !== "all") {
      fetchPods(targetNs)
        .then((p) => setTargetPods(p.filter((pod) => pod.status === "Running")))
        .catch(() => setTargetPods([]));
    } else {
      setTargetPods([]);
    }
  }, [targetNs]);

  // Load source pods when source namespace changes
  useEffect(() => {
    setSourcePod("");
    if (sourceNs) {
      fetchPods(sourceNs)
        .then((p) => setSourcePods(p.filter((pod) => pod.status === "Running")))
        .catch(() => setSourcePods([]));
    } else {
      setSourcePods([]);
    }
  }, [sourceNs]);

  const getTestProcess = (l: LatencyResult) => {
    const sourceParts = l.source.split("/");
    const srcNs = sourceParts[0];
    const srcPod = sourceParts.slice(1).join("/");
    const targetParts = l.target_service.split("/");
    const tgtNs = targetParts[0];
    const targetSvc = targetParts.slice(1).join("/");
    const svc = data?.services.find((s) => s.namespace === tgtNs && s.name === targetSvc);
    const port = svc?.ports[0]?.port ?? 80;
    const targetUrl = `http://${targetSvc}.${tgtNs}.svc.cluster.local:${port}/`;
    const crossNs = srcNs !== tgtNs;

    return {
      sourceNs: srcNs,
      sourcePod: srcPod,
      targetNs: tgtNs,
      targetSvc,
      port,
      targetUrl,
      crossNs,
      command: `kubectl exec ${srcPod} -n ${srcNs} -- curl -s -o /dev/null -w '%{time_total}' --connect-timeout 3 --max-time 5 ${targetUrl}`,
    };
  };

  return (
    <div className="network-page">
      <div className="page-header">
        <h1>Network Latency</h1>
        <div className="header-controls">
          <button className="refresh-btn" onClick={() => load()}>Refresh</button>
        </div>
      </div>

      {/* Source / Target control bar */}
      <div className="latency-controls">
        <div className="control-group">
          <label className="control-label">Source</label>
          <select value={sourceNs} onChange={(e) => setSourceNs(e.target.value)} className="ns-select">
            <option value="">Namespace (auto)</option>
            {namespaces.map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
          </select>
          <select
            value={sourcePod}
            onChange={(e) => setSourcePod(e.target.value)}
            className="ns-select"
            disabled={!sourceNs}
          >
            <option value="">{sourceNs ? "Pod (auto)" : "Select namespace first"}</option>
            {sourcePods.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
        </div>
        <span className="control-arrow">&rarr;</span>
        <div className="control-group">
          <label className="control-label">Target</label>
          <select value={targetNs} onChange={(e) => setTargetNs(e.target.value)} className="ns-select">
            <option value="all">All Namespaces</option>
            {namespaces.map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
          </select>
          <select
            value={targetPod}
            onChange={(e) => setTargetPod(e.target.value)}
            className="ns-select"
            disabled={!targetNs || targetNs === "all"}
          >
            <option value="">{targetNs && targetNs !== "all" ? "All Pods (services)" : "Select namespace first"}</option>
            {targetPods.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
        </div>
        <button
          className="refresh-btn latency-btn"
          onClick={() => load(true)}
          disabled={testingLatency}
        >
          {testingLatency ? "Testing..." : "Test Latency"}
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <div className="page-loading">Loading network info...</div>
      ) : (
        <>
          {/* Services table */}
          <div className="section-header"><h2>Services ({data?.services.length ?? 0})</h2></div>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Namespace</th>
                  <th>Type</th>
                  <th>ClusterIP</th>
                  <th>Ports</th>
                  <th>Endpoints</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data?.services.map((s) => (
                  <tr key={`${s.namespace}/${s.name}`} className={!s.has_endpoints ? "row-critical" : ""}>
                    <td className="pod-name">{s.name}</td>
                    <td className="text-muted">{s.namespace}</td>
                    <td>{s.type}</td>
                    <td className="mono-cell">{s.clusterIP}</td>
                    <td className="mono-cell">{s.ports.map((p) => `${p.port}/${p.protocol}`).join(", ")}</td>
                    <td>{s.endpoint_count}</td>
                    <td>
                      {s.has_endpoints ? (
                        <span className="status-badge ok">Active</span>
                      ) : (
                        <span className="status-badge critical">No Endpoints</span>
                      )}
                    </td>
                  </tr>
                ))}
                {(!data || data.services.length === 0) && (
                  <tr><td colSpan={7} className="empty-cell">No services found</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Latency results */}
          {data?.latency_tested && data.latency_results.length > 0 && (
            <>
              <div className="section-header"><h2>Latency Results</h2></div>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Target Service</th>
                      <th>Latency (ms)</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.latency_results.map((l, i) => (
                      <tr key={i} className={l.status === "unreachable" ? "row-critical" : l.status === "slow" ? "mismatch-row" : ""}>
                        <td className="text-muted">{l.source}</td>
                        <td>{l.target_service}</td>
                        <td className="mono-cell">{l.latency_ms >= 0 ? `${l.latency_ms}ms` : "\u2014"}</td>
                        <td className="latency-status-cell">
                          <span className={`status-badge ${l.status === "ok" ? "ok" : l.status === "slow" ? "warning" : "critical"}`}>
                            {l.status}
                          </span>
                          <button className="check-btn" onClick={() => setCheckResult(l)} title="View test process">
                            Check
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Network issues */}
          {data && data.network_issues.length > 0 && (
            <>
              <div className="section-header"><h2>Network Issues</h2></div>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr><th>Name</th><th>Namespace</th><th>Message</th><th>Timestamp</th></tr>
                  </thead>
                  <tbody>
                    {data.network_issues.map((issue, i) => (
                      <tr key={i} className="row-critical">
                        <td>{issue.name}</td>
                        <td>{issue.namespace}</td>
                        <td>{issue.message}</td>
                        <td className="text-muted">{issue.timestamp}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Network policies */}
          {data && data.network_policies.length > 0 && (
            <>
              <div className="section-header"><h2>Network Policies ({data.network_policies.length})</h2></div>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr><th>Policy</th><th>Namespace</th><th>Pod Selector</th></tr>
                  </thead>
                  <tbody>
                    {data.network_policies.map((np, i) => (
                      <tr key={i}>
                        <td>{np.name}</td>
                        <td>{np.namespace}</td>
                        <td className="mono-cell">{JSON.stringify(np.pod_selector)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {/* Test Process Modal */}
      {checkResult && (() => {
        const tp = getTestProcess(checkResult);
        return (
          <div className="trace-overlay" onClick={() => setCheckResult(null)}>
            <div className="trace-modal" onClick={(e) => e.stopPropagation()}>
              <div className="trace-header">
                <h2>
                  Latency Test Process
                  {tp.crossNs && <span className="badge-cross-ns">cross-namespace</span>}
                </h2>
                <button className="close-btn" onClick={() => setCheckResult(null)}>&times;</button>
              </div>
              <div className="trace-body">
                <div className="test-process-section">
                  <h3 className="tp-heading">Test Summary</h3>
                  <table className="data-table tp-table">
                    <tbody>
                      <tr><td className="tp-label">Source Pod</td><td className="mono-cell">{tp.sourcePod}</td></tr>
                      <tr><td className="tp-label">Source Namespace</td><td>{tp.sourceNs}</td></tr>
                      <tr><td className="tp-label">Target Service</td><td className="mono-cell">{tp.targetSvc}</td></tr>
                      <tr><td className="tp-label">Target Namespace</td><td>{tp.targetNs}</td></tr>
                      <tr><td className="tp-label">Target Port</td><td>{tp.port}</td></tr>
                      <tr><td className="tp-label">Resolved URL</td><td className="mono-cell">{tp.targetUrl}</td></tr>
                      <tr>
                        <td className="tp-label">Cross-Namespace</td>
                        <td>{tp.crossNs ? "Yes — traffic crosses namespace boundary" : "No — same namespace"}</td>
                      </tr>
                      <tr>
                        <td className="tp-label">Measured Latency</td>
                        <td>
                          <span className={`status-badge ${checkResult.status === "ok" ? "ok" : checkResult.status === "slow" ? "warning" : "critical"}`}>
                            {checkResult.latency_ms >= 0 ? `${checkResult.latency_ms}ms` : "unreachable"}
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <td className="tp-label">Verdict</td>
                        <td>
                          <span className={`status-badge ${checkResult.status === "ok" ? "ok" : checkResult.status === "slow" ? "warning" : "critical"}`}>
                            {checkResult.status === "ok" ? "Healthy" : checkResult.status === "slow" ? "Degraded" : "Unreachable"}
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>

                  <h3 className="tp-heading">Test Process (Step-by-Step)</h3>
                  <div className="tp-steps">
                    <div className="tp-step">
                      <span className="tp-step-num">1</span>
                      <div>
                        <strong>Select source pod</strong>
                        <p className="text-muted">User picks a source namespace and pod to curl FROM.{tp.crossNs ? " Source and target are in different namespaces — this tests cross-namespace network path." : ""} Selected: <code>{tp.sourcePod}</code> in <code>{tp.sourceNs}</code></p>
                      </div>
                    </div>
                    <div className="tp-step">
                      <span className="tp-step-num">2</span>
                      <div>
                        <strong>Resolve target URL via K8s DNS</strong>
                        <p className="text-muted">Constructs fully-qualified Kubernetes internal DNS: <code>{tp.targetUrl}</code>{tp.crossNs ? " — the FQDN includes the target namespace, enabling cross-namespace resolution." : ""}</p>
                      </div>
                    </div>
                    <div className="tp-step">
                      <span className="tp-step-num">3</span>
                      <div>
                        <strong>Execute curl via kubectl exec</strong>
                        <p className="text-muted">Runs curl inside the source pod with timing measurement:</p>
                        <pre className="tp-command">{tp.command}</pre>
                      </div>
                    </div>
                    <div className="tp-step">
                      <span className="tp-step-num">4</span>
                      <div>
                        <strong>Measure total time</strong>
                        <p className="text-muted"><code>curl -w '%{"{time_total}"}'</code> outputs the total request time in seconds. This includes DNS resolution, TCP handshake, TLS negotiation, request transfer, and response transfer.</p>
                      </div>
                    </div>
                    <div className="tp-step">
                      <span className="tp-step-num">5</span>
                      <div>
                        <strong>Convert &amp; classify</strong>
                        <p className="text-muted">
                          Seconds &times; 1000 = milliseconds.
                          Classification: <span className="status-badge ok">ok</span> &lt; 1000ms,{" "}
                          <span className="status-badge warning">slow</span> &ge; 1000ms,{" "}
                          <span className="status-badge critical">unreachable</span> on error/timeout.
                        </p>
                      </div>
                    </div>
                  </div>

                  <h3 className="tp-heading">Curl Flags Explained</h3>
                  <table className="data-table tp-table">
                    <thead>
                      <tr><th>Flag</th><th>Purpose</th></tr>
                    </thead>
                    <tbody>
                      <tr><td className="mono-cell">-s</td><td>Silent mode (no progress bar)</td></tr>
                      <tr><td className="mono-cell">-o /dev/null</td><td>Discard response body (only timing matters)</td></tr>
                      <tr><td className="mono-cell">-w '%{"{time_total}"}'</td><td>Output total elapsed time in seconds</td></tr>
                      <tr><td className="mono-cell">--connect-timeout 3</td><td>TCP connection timeout: 3 seconds</td></tr>
                      <tr><td className="mono-cell">--max-time 5</td><td>Total request timeout: 5 seconds</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
