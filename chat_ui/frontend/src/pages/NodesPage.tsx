import { useEffect, useState } from "react";
import { fetchNodes } from "../api/clusterApi";
import type { ClusterNode } from "../api/clusterApi";

export function NodesPage() {
  const [nodes, setNodes] = useState<ClusterNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchNodes();
      setNodes(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load nodes");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="nodes-page">
      <div className="page-header">
        <h1>Nodes</h1>
        <button className="refresh-btn" onClick={load}>Refresh</button>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <div className="page-loading">Loading nodes...</div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Roles</th>
                <th>Version</th>
                <th>OS</th>
                <th>Kernel</th>
                <th>Runtime</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((n) => (
                <tr key={n.name}>
                  <td className="node-name">{n.name}</td>
                  <td>
                    <span className={`status-dot ${n.status === "Ready" ? "green" : "red"}`} />
                    {n.status}
                  </td>
                  <td>{n.roles}</td>
                  <td>{n.version}</td>
                  <td className="text-muted">{n.os}</td>
                  <td className="text-muted">{n.kernel}</td>
                  <td className="text-muted">{n.container_runtime}</td>
                </tr>
              ))}
              {nodes.length === 0 && (
                <tr><td colSpan={7} className="empty-cell">No nodes found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
