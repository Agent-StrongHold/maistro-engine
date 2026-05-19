import { type ReactNode, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useUser } from "../App";

const nav = [
  { to: "/dashboard", icon: "\uD83C\uDFE0", label: "Dashboard" },
  { to: "/chat", icon: "\uD83D\uDCAC", label: "Chat" },
  { to: "/missions", icon: "\uD83C\uDFAF", label: "Missions" },
  { to: "/dags", icon: "\uD83DD\uDC00", label: "DAGs" },
  { to: "/schedules", icon: "\u23F1", label: "Schedules" },
  { to: "/agents", icon: "\uD83E\uDDE0", label: "Agents" },
  { to: "/skills", icon: "\u25C8", label: "Skills" },
  { to: "/mcp", icon: "\u229E", label: "MCP" },
  { to: "/topology", icon: "\uD83D\uDD17", label: "Topology" },
  { to: "/messages", icon: "\uD83D\uDCCB", label: "Messages" },
  { to: "/quotas", icon: "\uD83D\uDCCA", label: "Quotas" },
  { to: "/audit", icon: "\uD83D\uDD12", label: "Audit" },
  { to: "/cli", icon: "\u203A_", label: "CLI" },
  { to: "/containers", icon: "\u2B21", label: "Containers" },
  { to: "/evolution", icon: "\u26A1", label: "Evolution" },
  { to: "/memory", icon: "\u25D1", label: "Memory" },
  { to: "/settings", icon: "\u2699", label: "Settings" },
];

async function logout() {
  await fetch("/v1/auth/logout", { method: "POST" });
  window.location.href = "/";
}

export function AppShell({ children }: { children?: ReactNode }) {
  const user = useUser();
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="app-shell">
      <button
        className="hamburger"
        onClick={() => setDrawerOpen(true)}
        aria-label="Open menu"
      >
        <span /><span /><span />
      </button>

      <div className={`drawer-overlay${drawerOpen ? " open" : ""}`} onClick={() => setDrawerOpen(false)} />

      <nav className={`drawer${drawerOpen ? " open" : ""}`}>
        <div className="drawer-header">
          <span style={{ fontFamily: "var(--hand)", fontSize: 20, fontWeight: 700 }}>Hive Conductor</span>
          <button className="drawer-close" onClick={() => setDrawerOpen(false)} aria-label="Close menu">&#x2715;</button>
        </div>
        {user && (
          <div className="drawer-user">
            <span className="hex-badge" style={{ background: user.role === "admin" ? "var(--danger)" : "var(--accent)", color: "var(--paper)" }}>{user.role}</span>
            <span style={{ fontFamily: "var(--mono)", fontSize: 10 }}>{user.username}</span>
            {user.did && <span style={{ fontSize: 8, opacity: 0.6 }} title={user.did}>DID</span>}
          </div>
        )}
        <div className="drawer-nav">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `drawer-link${isActive ? " active" : ""}`}
              end={item.to === "/cli"}
              onClick={() => setDrawerOpen(false)}
            >
              <span className="drawer-link-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <button className="drawer-link" style={{ borderTop: "1px solid var(--rule)", marginTop: 8 }} onClick={() => void logout()}>
          <span className="drawer-link-icon">&#x2192;</span>
          <span>Sign out {user?.username}</span>
        </button>
      </nav>

      <nav className="icon-sidebar">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `nav-icon${isActive ? " active" : ""}`}
            end={item.to === "/cli"}
            title={item.label}
          >
            {item.icon}
          </NavLink>
        ))}
        <div style={{ flex: 1 }} />
        <div
          className="nav-icon"
          style={{ color: "var(--pencil)", fontSize: 10, fontFamily: "var(--mono)", lineHeight: 1.1, textAlign: "center", cursor: "pointer", padding: "6px 0" }}
          onClick={() => void logout()}
          title={`Sign out ${user?.username ?? ""}`}
        >
          {user?.username?.slice(0, 2).toUpperCase() ?? "??"}
          <div style={{ fontSize: 7, marginTop: 2 }}>&#x2192;out</div>
        </div>
      </nav>
      <main className="main-content">
        {children ?? <Outlet />}
      </main>
    </div>
  );
}
