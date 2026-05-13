import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

const nav = [
  { to: "/chat", label: "Chat" },
  { to: "/missions", label: "Missions" },
  { to: "/schedules", label: "Schedules" },
  { to: "/skills", label: "Skills" },
  { to: "/agents", label: "Agents" },
  { to: "/mcp", label: "MCP" },
  { to: "/cli", label: "CLI" },
  { to: "/cli/canvas", label: "Design studio" },
  { to: "/containers", label: "Containers" },
  { to: "/memory", label: "Memory" },
  { to: "/settings", label: "Settings" },
  { to: "/install", label: "Install" },
];

export function AppShell({ children }: { children?: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">Hive Conductor</div>
        <nav className="nav">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
              end={item.to === "/cli"}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main">{children ?? <Outlet />}</main>
    </div>
  );
}
