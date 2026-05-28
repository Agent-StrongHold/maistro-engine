import { type ReactNode, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useUser } from "../App";
import { ModeToggle } from "./ModeToggle";
import { usePmPoc } from "../context/PocMode";
import {
  PM_NAV_CREDENTIALS,
  PM_NAV_DRAFTS,
  PM_NAV_INTEGRATIONS,
  PM_NAV_MISSIONS,
  PM_NAV_PROGRAM,
  PM_PRODUCT_NAME,
} from "../lib/pmBranding";

const fullNav = [
  { to: "/chat", icon: "💬", label: "Chat" },
  { to: "/dashboard", icon: "📊", label: "Dashboard" },
  { to: "/agents", icon: "🤖", label: "Agents" },
  { to: "/settings", icon: "⚙", label: "Settings" },
];

const pocNav = [
  { to: "/chat", icon: "\uD83D\uDCAC", label: "Chat" },
  { to: "/dashboard", icon: "\uD83D\uDCCA", label: "Dashboard" },
  { to: "/knowledge", icon: "\uD83E\uDDE0", label: "Knowledge" },
  { to: "/agents", icon: "\uD83D\uDC1D", label: PM_NAV_PROGRAM },
  { to: "/missions", icon: "\uD83C\uDFAF", label: PM_NAV_MISSIONS },
  { to: "/mcp", icon: "\u229E", label: PM_NAV_INTEGRATIONS },
  { to: "/credentials", icon: "\uD83D\uDD11", label: PM_NAV_CREDENTIALS },
  { to: "/settings", icon: "\u2699", label: "Settings" },
];

async function logout() {
  try {
    await fetch("/v1/auth/logout", { method: "POST", credentials: "same-origin" });
  } catch {
    // best effort — even if it fails, redirecting lets the user log in fresh.
  }
  // Stay inside the Hive app (which auto-shows Login when no session); going
  // to "/" dumps the user at the MAISTROcatalog with no obvious way back.
  window.location.href = import.meta.env.BASE_URL || "/";
}

export function AppShell({ children }: { children?: ReactNode }) {
  const user = useUser();
  const pmPoc = usePmPoc();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const nav = pmPoc ? pocNav : fullNav;
  const shellTitle = pmPoc ? PM_PRODUCT_NAME : "Hive Conductor";

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
          <span style={{ fontFamily: "var(--hand)", fontSize: 20, fontWeight: 700 }}>{shellTitle}</span>
          <ModeToggle />
          <button className="drawer-close" onClick={() => setDrawerOpen(false)} aria-label="Close menu">&#x2715;</button>
        </div>
        {pmPoc ? (
          <div style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--pencil)", padding: "0 12px 8px" }}>
            PM demo · 6 agents · gated Jira drafts
          </div>
        ) : (
          <div style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--pencil)", padding: "0 12px 8px" }}>
            Multi-agent · multi-MCP · container sandbox
          </div>
        )}
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
            <span aria-hidden>{item.icon}</span>
            <span className="nav-icon-label">{item.label}</span>
          </NavLink>
        ))}
        <div style={{ flex: 1 }} />
        {user && (
          <div
            className="nav-icon"
            style={{
              color: "var(--pencil)",
              fontSize: 9,
              fontFamily: "var(--mono)",
              lineHeight: 1.2,
              textAlign: "center",
              padding: "6px 0",
              borderTop: "1px solid var(--rule)",
              marginTop: 4,
            }}
            title={`Signed in as ${user.username} (${user.role}) — click to sign out`}
          >
            <span
              style={{
                display: "inline-block",
                padding: "1px 4px",
                borderRadius: 2,
                background: user.role === "admin" ? "var(--danger)" : "var(--accent)",
                color: "var(--paper)",
                fontWeight: 700,
                fontSize: 7,
                letterSpacing: 0.5,
              }}
            >
              {(user.role || "user").toUpperCase()}
            </span>
            <div style={{ fontSize: 8, marginTop: 3, color: "var(--ink)" }}>
              {user.username}
            </div>
          </div>
        )}
        <button
          type="button"
          className="nav-icon"
          style={{
            background: "none",
            border: "none",
            color: "var(--danger)",
            cursor: "pointer",
            fontSize: 18,
            padding: "10px 0",
          }}
          onClick={() => void logout()}
          title="Sign out"
          aria-label="Sign out"
        >
          <span aria-hidden>⎋</span>
          <span className="nav-icon-label" style={{ color: "var(--danger)" }}>Sign out</span>
        </button>
      </nav>
      <main className="main-content">
        {children ?? <Outlet />}
      </main>
    </div>
  );
}
