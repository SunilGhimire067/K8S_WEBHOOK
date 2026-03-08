import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { fetchEvents } from "../api/eventsApi";
import type { K8sEvent } from "../types/events";
import { SeverityBadge } from "../components/events/SeverityBadge";

const SEVERITY_FILTERS = ["all", "critical", "warning", "info"];

export function EventExplorerPage() {
  const [events, setEvents] = useState<K8sEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [severity, setSeverity] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [isLive, setIsLive] = useState(true);
  const navigate = useNavigate();

  const loadEvents = useCallback(async () => {
    try {
      const data = await fetchEvents({ severity, search, limit: 50 });
      setEvents(data.events);
      setTotal(data.total);
    } catch (err) {
      console.error("Event load error:", err);
    } finally {
      setLoading(false);
    }
  }, [severity, search]);

  useEffect(() => {
    setLoading(true);
    loadEvents();
  }, [loadEvents]);

  // Auto-poll when live
  useEffect(() => {
    if (!isLive) return;
    const interval = setInterval(loadEvents, 5000);
    return () => clearInterval(interval);
  }, [isLive, loadEvents]);

  const formatTime = (ts: string) => {
    if (!ts) return "-";
    const d = new Date(ts);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "Just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    return d.toLocaleDateString();
  };

  return (
    <div className="event-explorer-page">
      <div className="page-header">
        <div>
          <h1>Event Explorer</h1>
          <p className="page-subtitle">{total} total events</p>
        </div>
        <div className="header-actions">
          <button
            className={`live-toggle ${isLive ? "active" : ""}`}
            onClick={() => setIsLive(!isLive)}
          >
            <span className={`live-dot ${isLive ? "live" : ""}`} />
            {isLive ? "LIVE" : "PAUSED"}
          </button>
          <button className="refresh-btn" onClick={loadEvents}>
            Refresh
          </button>
        </div>
      </div>

      <div className="event-filters">
        <div className="filter-buttons">
          {SEVERITY_FILTERS.map((s) => (
            <button
              key={s}
              className={`filter-btn ${severity === s ? "active" : ""} ${s}`}
              onClick={() => setSeverity(s)}
            >
              {s.toUpperCase()}
            </button>
          ))}
        </div>
        <input
          type="text"
          className="search-input"
          placeholder="Search events..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <div className="page-loading">Loading events...</div>
      ) : (
        <div className="table-container">
          <table className="data-table event-table">
            <thead>
              <tr>
                <th>TYPE</th>
                <th>REASON</th>
                <th>OBJECT</th>
                <th>MESSAGE</th>
                <th>TIME</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr
                  key={e.event_id}
                  className="clickable-row"
                  onClick={() => navigate(`/ai-insights?event=${e.event_id}`)}
                >
                  <td>
                    <SeverityBadge severity={e.severity} />
                  </td>
                  <td className="reason-cell">{e.reason}</td>
                  <td className="object-cell">
                    <span className="object-name">{e.name}</span>
                    <span className="object-meta">
                      {e.kind} &middot; {e.namespace}
                    </span>
                  </td>
                  <td className="msg-cell">{(e.message || "").slice(0, 120)}</td>
                  <td className="time-cell">{formatTime(e.created_at)}</td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr>
                  <td colSpan={5} className="empty-cell">
                    No events found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div
        className="ai-insights-card"
        onClick={() => navigate("/ai-insights")}
      >
        <span className="ai-card-icon">&#10024;</span>
        <div>
          <strong>AI Insights</strong>
          <p>Click any event row or open chat to analyze</p>
        </div>
      </div>
    </div>
  );
}
