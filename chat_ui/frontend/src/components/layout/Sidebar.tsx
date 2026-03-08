import { NavLink } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { useChatContext } from "../../context/ChatContext";

export function Sidebar() {
  const { logout } = useAuth();
  const { isLoading } = useChatContext();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-icon">&#9096;</span>
        <span className="brand-text">Sentinel K8s</span>
      </div>

      <nav className="sidebar-nav">
        <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="nav-icon">&#9632;</span>
          Dashboard
        </NavLink>
        <NavLink to="/events" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="nav-icon">&#9888;</span>
          Event Explorer
        </NavLink>
        <NavLink to="/nodes" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="nav-icon">&#8962;</span>
          Nodes
        </NavLink>
        <NavLink to="/logs" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="nav-icon">&#9776;</span>
          Logs
        </NavLink>
        <NavLink to="/resources" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="nav-icon">&#9881;</span>
          Resources
        </NavLink>
        <NavLink to="/jvm" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="nav-icon">&#9749;</span>
          JVM Details
        </NavLink>
        <NavLink to="/network" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="nav-icon">&#8644;</span>
          Network
        </NavLink>
        <NavLink to="/ai-insights" className={({ isActive }) => `nav-item ${isActive ? "active" : ""} ${isLoading ? "ai-busy" : ""}`}>
          <span className="nav-icon">&#10024;</span>
          AI Insights
          {isLoading && <span className="ai-processing-dot" />}
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="nav-icon">&#9881;</span>
          Settings
        </NavLink>
      </nav>

      <div className="sidebar-footer">
        <button className="logout-btn" onClick={logout}>
          Logout
        </button>
      </div>
    </aside>
  );
}
