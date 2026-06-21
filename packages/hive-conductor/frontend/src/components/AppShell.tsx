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
    <div className="app-shell">
      {/* Sidebar */}
      <nav className="app-sidebar">
        <div className="app-sidebar-brand">
          <span className="app-logo">✦</span>
          <span className="app-brand-text">Maistro</span>
        </div>

        <div className="app-nav-list">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `app-nav-item ${isActive ? "app-nav-item--active" : ""}`}
            >
              <span className="app-nav-label">{item.label}</span>
            </NavLink>
          ))}
        </div>

        <div className="app-sidebar-footer">
          {user && (
            <div className="app-user-badge">
              <span className="app-user-name">{user.username}</span>
            </div>
          )}
          <button className="app-nav-item app-logout" onClick={logout}>
            Sign out
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main className="app-main">
        {children ?? <Outlet />}
      </main>
    </div>
  );
}
