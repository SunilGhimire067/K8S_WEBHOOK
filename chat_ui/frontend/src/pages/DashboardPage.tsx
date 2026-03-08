import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchEventStats } from "../api/eventsApi";
import { fetchEvents } from "../api/eventsApi";
import { fetchNodes } from "../api/clusterApi";
import type { EventStats, K8sEvent } from "../types/events";
import type { ClusterNode } from "../api/clusterApi";
import { SeverityBadge } from "../components/events/SeverityBadge";

export function DashboardPage() {
  const [stats, setStats] = useState<EventStats | null>(null);
  const [recentEvents, setRecentEvents] = useState<K8sEvent[]>([]);
  const [nodes, setNodes] = useState<ClusterNode[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    async function load() {
      const [statsRes, evtsRes, nodesRes] = await Promise.allSettled([
        fetchEventStats(),
        fetchEvents({ limit: 5 }),
        fetchNodes(),
      ]);
      if (statsRes.status === "fulfilled") setStats(statsRes.value);
      if (evtsRes.status === "fulfilled") setRecentEvents(evtsRes.value.events);
      if (nodesRes.status === "fulfilled") setNodes(nodesRes.value);
      else console.warn("Nodes fetch failed:", (nodesRes as PromiseRejectedResult).reason);
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return <div className="page-loading">Loading dashboard...</div>;
  }

  const critical = stats?.by_severity?.critical ?? 0;
  const warning = stats?.by_severity?.warning ?? 0;
  const info = stats?.by_severity?.info ?? 0;
  const total = stats?.total ?? 0;

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p className="page-subtitle">Cluster overview and health status</p>
      </div>

      <div className="stat-cards">
        <div className="stat-card">
          <div className="stat-value">{total}</div>
          <div className="stat-label">Total Events</div>
        </div>
        <div className="stat-card critical">
          <div className="stat-value">{critical}</div>
          <div className="stat-label">Critical</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-value">{warning}</div>
          <div className="stat-label">Warning</div>
        </div>
        <div className="stat-card info">
          <div className="stat-value">{info}</div>
          <div className="stat-label">Normal</div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="dashboard-section">
          <div className="section-header">
            <h2>Recent Events</h2>
            <button className="link-btn" onClick={() => navigate("/events")}>
              View all
            </button>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Reason</th>
                <th>Object</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {recentEvents.map((e) => (
                <tr key={e.event_id} className="clickable-row" onClick={() => navigate(`/ai-insights?event=${e.event_id}`)}>
                  <td><SeverityBadge severity={e.severity} /></td>
                  <td>{e.reason}</td>
                  <td className="text-muted">{e.namespace}/{e.name}</td>
                  <td className="msg-cell">{(e.message || "").slice(0, 80)}</td>
                </tr>
              ))}
              {recentEvents.length === 0 && (
                <tr><td colSpan={4} className="empty-cell">No events recorded</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="dashboard-section">
          <h2>Node Status</h2>
          <table className="data-table">
            <thead>
              <tr>
                <th>Node</th>
                <th>Status</th>
                <th>Role</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((n) => (
                <tr key={n.name}>
                  <td>{n.name}</td>
                  <td>
                    <span className={`status-dot ${n.status === "Ready" ? "green" : "red"}`} />
                    {n.status}
                  </td>
                  <td>{n.roles}</td>
                  <td className="text-muted">{n.version}</td>
                </tr>
              ))}
              {nodes.length === 0 && (
                <tr><td colSpan={4} className="empty-cell">No nodes found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
