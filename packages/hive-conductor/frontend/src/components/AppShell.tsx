import { type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useUser } from "../App";

const NAV_ITEMS = [
  { to: "/overview", label: "Overview", icon: "home" },
  { to: "/chat", label: "Chat", icon: "message" },
  { to: "/dashboard", label: "Dashboard", icon: "grid" },
  { to: "/dags", label: "Flows", icon: "branch" },
  { to: "/knowledge", label: "Inner Temple", icon: "brain" },
  { to: "/decks", label: "Decks", icon: "presentation" },
  { to: "/agents", label: "Program", icon: "hexagon" },
  { to: "/missions", label: "Activity", icon: "target" },
  { to: "/mcp", label: "Integrations", icon: "plug" },
  { to: "/credentials", label: "Credentials", icon: "key" },
  { to: "/settings", label: "Settings", icon: "settings" },
];

async function logout() {
  try { await fetch("/v1/auth/logout", { method: "POST", credentials: "same-origin" }); } catch {}
  window.location.href = import.meta.env.BASE_URL || "/";
}

export function AppShell({ children }: { children?: ReactNode }) {
  const user = useUser();

  return (
    <div className="fantasia-shell">
      {/* Sidebar */}
      <nav className="fantasia-sidebar">
        <div className="fantasia-sidebar-brand">
          <span className="fantasia-logo">✦</span>
          <span className="fantasia-brand-text">Fantasia</span>
        </div>

        <div className="fantasia-nav-list">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `fantasia-nav-item ${isActive ? "fantasia-nav-item--active" : ""}`}
            >
              <span className="fantasia-nav-label">{item.label}</span>
            </NavLink>
          ))}
        </div>

        <div className="fantasia-sidebar-footer">
          {user && (
            <div className="fantasia-user-badge">
              <span className="fantasia-user-name">{user.username}</span>
            </div>
          )}
          <button className="fantasia-nav-item fantasia-logout" onClick={logout}>
            Sign out
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main className="fantasia-main">
        {children ?? <Outlet />}
      </main>
    </div>
  );
}
