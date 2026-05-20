import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPost } from "../lib/api";
import { LoadingSpinner, PageHeader, StatusDot, useToast } from "../components/shared";

type AgentStatus = "idle" | "busy" | "offline" | "error";
type Role = "queen" | "worker" | "scout" | "drone" | "guard";

type Agent = {
  id: string;
  name: string;
  description: string;
  model: string;
  status: AgentStatus;
  capabilities: string[];
  config: Record<string, unknown>;
};

type Mission = {
  id: string;
  name: string;
  status: string;
  progress: number;
  assigned_agents: string[];
};

type HealthResponse = {
  status: string;
  version: string;
  uptime_seconds: number;
};

type PendingConfirm = {
  confirm_id: string;
  status: string;
  message: string;
  target: string;
  created_at: number;
  timeout_seconds: number;
  result?: string;
};

const ROLE_COLORS: Record<Role, string> = {
  queen: "#d4a017",
  worker: "#2b2419",
  scout: "#5a9a4a",
  drone: "#6b5d49",
  guard: "#3a6a9a",
};

const ROLE_ICONS: Record<Role, string> = {
  queen: "\u{1F451}",
  worker: "\u{1F41D}",
  scout: "\u{1F50D}",
  drone: "\u{1F916}",
  guard: "\u{1F6E1}\uFE0F",
};

const AGENT_STATUS_MAP: Record<AgentStatus, "running" | "idle" | "error" | "busy"> = {
  idle: "idle",
  busy: "busy",
  offline: "idle",
  error: "error",
};

type QuotaProvider = {
  provider: string;
  used_tokens: number;
  free_tokens: number;
  remaining_tokens: number;
  usage_pct: number;
  status: string;
};

const QUOTA_COLORS = ["#5a9a4a", "#d4a017", "#3a6a9a", "#7a5af5", "#c4452a", "#e8a03a", "#5a4a9a"];

const PULSE_CSS_ID = "hc-dash-pulse";

function ensurePulseCss() {
  if (document.getElementById(PULSE_CSS_ID)) return;
  const s = document.createElement("style");
  s.id = PULSE_CSS_ID;
  s.textContent = "@keyframes hc-dash-hex-pulse{0%,100%{opacity:1}50%{opacity:.5}}";
  document.head.appendChild(s);
}

function agentRole(a: Agent): Role {
  const n = a.name.toLowerCase();
  const caps = a.capabilities.map((c) => c.toLowerCase());
  if (n.includes("conductor") || n.includes("orchestrator") || n.includes("queen")) return "queen";
  if (caps.includes("security") || n.includes("guard") || n.includes("sentinel")) return "guard";
  if (caps.includes("research") || n.includes("scout") || n.includes("phantom")) return "scout";
  if (caps.includes("monitoring") || n.includes("monitor") || n.includes("heartbeat")) return "drone";
  return "worker";
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function hexPoints(cx: number, cy: number, r: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const angle = -Math.PI / 2 + (i * Math.PI) / 3;
    pts.push(`${(cx + r * Math.cos(angle)).toFixed(1)},${(cy + r * Math.sin(angle)).toFixed(1)}`);
  }
  return pts.join(" ");
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + "\u2026" : s;
}

export default function Dashboard() {
  const toast = useToast();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [hoveredHex, setHoveredHex] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [pendingConfirms, setPendingConfirms] = useState<PendingConfirm[]>([]);
  const [quotas, setQuotas] = useState<QuotaProvider[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [a, t, h, q] = await Promise.all([
        apiGet<Agent[]>("/v1/agents"),
        apiGet<Mission[]>("/v1/tasks"),
        apiGet<HealthResponse>("/health"),
        apiGet<QuotaProvider[]>("/v1/quotas/providers").catch(() => []),
      ]);
      setAgents(a);
      setMissions(t);
      setHealth(h);
      setQuotas(q);
    } catch {
      toast("Failed to load dashboard data", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const pollConfirms = useCallback(async () => {
    try {
      const all = await apiGet<PendingConfirm[]>("/v1/confirms");
      setPendingConfirms(all.filter((c) => c.status === "pending"));
    } catch { /* */ }
  }, []);

  useEffect(() => {
    ensurePulseCss();
    void load();
    void pollConfirms();
    pollRef.current = window.setInterval(() => void pollConfirms(), 4000);
    return () => { if (pollRef.current) window.clearInterval(pollRef.current); };
  }, [load, pollConfirms]);

  async function respondConfirm(confirmId: string, response: "approved" | "denied") {
    try {
      await apiPost(`/v1/confirms/${confirmId}/respond`, { response });
      await pollConfirms();
      toast(response === "approved" ? "Approved" : "Denied", response === "approved" ? "ok" : "warn");
    } catch {
      toast("Failed to respond", "error");
    }
  }

  if (loading) return <LoadingSpinner />;

  const activeAgents = agents.filter((a) => a.status === "busy" || a.status === "idle");
  const runningMissions = missions.filter((m) => m.status === "running");
  const completedMissions = missions.filter((m) => m.status === "completed");
  const activeMissions = missions.filter((m) => m.status === "running" || m.status === "pending");
  const defaultModel = agents.length > 0 ? agents[0].model : "\u2014";

  const hexR = 46;
  const hexW = Math.sqrt(3) * hexR;
  const hexH = 2 * hexR;
  const cols = 4;
  const pad = 30;
  const svgW = cols * hexW + hexW / 2 + pad * 2;
  const svgH = Math.ceil(Math.max(agents.length, 1) / cols) * (hexH * 0.75) + hexH * 0.25 + pad * 2 + 60;

  return (
    <div style={{ minHeight: "calc(100vh - 60px)", paddingBottom: 40 }}>
      <PageHeader
        title="Dashboard"
        subtitle="Your home base — see what's happening across your hive at a glance"
        helpHref="/docs#dashboard"
      />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
        <div className="stat-card">
          <div className="label">Agents</div>
          <div className="value" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
            <StatusDot status={activeAgents.length > 0 ? "running" : "idle"} />
            {activeAgents.length}/{agents.length} active
          </div>
        </div>
        <div className="stat-card">
          <div className="label">Missions</div>
          <div className="value">{runningMissions.length} running · {completedMissions.length} completed</div>
        </div>
        <div className="stat-card">
          <div className="label">Uptime</div>
          <div className="value">{health ? formatUptime(health.uptime_seconds) : "\u2014"}</div>
        </div>
        <div className="stat-card">
          <div className="label">Model</div>
          <div className="value" style={{ fontSize: 13 }}>{defaultModel}</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
        {([
          { label: "New Chat", icon: "\u{1F4AC}", to: "/chat" },
          { label: "New Mission", icon: "\u26A1", to: "/missions" },
          { label: "View DAGs", icon: "\u{1F517}", to: "/dags" },
        ] as const).map((action) => (
          <div
            key={action.label}
            onClick={() => navigate(action.to)}
            style={{
              flex: 1, padding: "10px 14px", border: "1.3px solid var(--rule)",
              borderRadius: 6, cursor: "pointer", textAlign: "center",
              background: "var(--comb-bg)", transition: "border-color 0.15s",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--rule)"; }}
          >
            <div style={{ fontSize: 20 }}>{action.icon}</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--ink)", marginTop: 4 }}>{action.label}</div>
          </div>
        ))}
      </div>

      {pendingConfirms.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontFamily: "var(--hand)", fontSize: 18, fontWeight: 700, marginBottom: 8, color: "var(--danger)" }}>
            Approval Required
            <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)", marginLeft: 8, fontWeight: 400 }}>
              {pendingConfirms.length} pending
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {pendingConfirms.map((c) => (
              <div key={c.confirm_id} className="card" style={{ borderLeft: "3px solid var(--danger)", padding: "10px 12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: "var(--hand)", fontSize: 15, fontWeight: 600 }}>{c.message}</div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginTop: 3 }}>
                      for {c.target} · {new Date(c.created_at * 1000).toLocaleTimeString()}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                    <button
                      onClick={() => void respondConfirm(c.confirm_id, "approved")}
                      style={{
                        padding: "4px 14px", borderRadius: 4, cursor: "pointer",
                        fontFamily: "var(--mono)", fontSize: 10, fontWeight: 600,
                        border: "1.3px solid var(--ok)", background: "var(--ok)",
                        color: "white",
                      }}
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => void respondConfirm(c.confirm_id, "denied")}
                      style={{
                        padding: "4px 14px", borderRadius: 4, cursor: "pointer",
                        fontFamily: "var(--mono)", fontSize: 10, fontWeight: 600,
                        border: "1.3px solid var(--danger)", background: "var(--danger)",
                        color: "white",
                      }}
                    >
                      Deny
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {agents.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontFamily: "var(--hand)", fontSize: 22, fontWeight: 700, marginBottom: 10 }}>
            The Hive
            <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)", marginLeft: 10, fontWeight: 400 }}>
              {agents.length} agents
            </span>
          </div>
          <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`} style={{ display: "block" }}>
            {agents.map((a, idx) => {
              const role = agentRole(a);
              const col = idx % cols;
              const row = Math.floor(idx / cols);
              const offsetX = row % 2 === 1 ? hexW / 2 : 0;
              const cx = pad + hexW / 2 + col * hexW + offsetX;
              const cy = pad + hexR + row * hexH * 0.75;
              const color = ROLE_COLORS[role];
              const isActive = a.status === "busy" || a.status === "idle";
              const isHovered = hoveredHex === a.id;
              return (
                <g
                  key={a.id}
                  style={{ cursor: "pointer" }}
                  onMouseEnter={() => setHoveredHex(a.id)}
                  onMouseLeave={() => setHoveredHex(null)}
                  onClick={() => setSelectedAgent(selectedAgent?.id === a.id ? null : a)}
                >
                  <polygon
                    points={hexPoints(cx, cy, hexR)}
                    fill={isHovered ? `${color}22` : `${color}0d`}
                    stroke={isHovered ? color : `${color}66`}
                    strokeWidth={isHovered ? 2.5 : 1.3}
                  />
                  {isActive && (
                    <polygon
                      points={hexPoints(cx, cy, hexR + 3)}
                      fill="none"
                      stroke={color}
                      strokeWidth={0.8}
                      opacity={0.25}
                      style={{ animation: "hc-dash-hex-pulse 2.5s ease-in-out infinite" }}
                    />
                  )}
                  <text x={cx} y={cy - 8} textAnchor="middle" dominantBaseline="central" fontSize={18} style={{ pointerEvents: "none" }}>
                    {ROLE_ICONS[role]}
                  </text>
                  <text x={cx} y={cy + 12} textAnchor="middle" fontSize={7.5} fontFamily="var(--mono)" fill="var(--ink)" style={{ pointerEvents: "none" }}>
                    {truncate(a.name, 11)}
                  </text>
                  <circle cx={cx} cy={cy + 22} r={2.5} fill={isActive ? "#5a9a4a" : "var(--pencil)"} style={{ pointerEvents: "none" }} />
                  {isHovered && (
                    <g>
                      <rect x={cx - 68} y={cy + hexR + 6} width={136} height={50} rx={4} fill="var(--paper)" stroke="var(--rule)" />
                      <text x={cx} y={cy + hexR + 20} textAnchor="middle" fontSize={9} fontFamily="var(--mono)" fill="var(--ink)" fontWeight={600} style={{ pointerEvents: "none" }}>{a.name}</text>
                      <text x={cx} y={cy + hexR + 32} textAnchor="middle" fontSize={7.5} fontFamily="var(--mono)" fill="var(--pencil)" style={{ pointerEvents: "none" }}>{a.model}</text>
                      <text x={cx} y={cy + hexR + 44} textAnchor="middle" fontSize={7.5} fontFamily="var(--mono)" fill="var(--pencil)" style={{ pointerEvents: "none" }}>
                        {a.status} · {a.capabilities.length} caps
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
          <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
            {(Object.keys(ROLE_COLORS) as Role[]).map((role) => (
              <div key={role} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ fontSize: 13 }}>{ROLE_ICONS[role]}</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: ROLE_COLORS[role], textTransform: "capitalize" }}>{role}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div>
          <div style={{ fontFamily: "var(--hand)", fontSize: 18, fontWeight: 700, marginBottom: 8 }}>
            Active Missions
            <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)", marginLeft: 8, fontWeight: 400 }}>
              {activeMissions.length}
            </span>
          </div>
          <div style={{ maxHeight: 280, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
            {activeMissions.length === 0 && (
              <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)", padding: 24, textAlign: "center", border: "1px dashed var(--rule)", borderRadius: 6 }}>
                No active missions
              </div>
            )}
            {activeMissions.map((m) => (
              <div
                key={m.id}
                onClick={() => navigate("/missions")}
                className="card"
                style={{ cursor: "pointer", padding: "8px 10px" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                  <span style={{
                    display: "inline-block", width: 7, height: 7, borderRadius: "50%",
                    background: m.status === "running" ? "var(--accent)" : "var(--pencil)",
                    animation: m.status === "running" ? "hc-dash-hex-pulse 1.5s ease-in-out infinite" : "none",
                    flexShrink: 0,
                  }} />
                  <span style={{ fontFamily: "var(--hand)", fontSize: 14, fontWeight: 600, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {m.name}
                  </span>
                  {m.assigned_agents.length > 0 && (
                    <span style={{
                      padding: "1px 6px", borderRadius: 3, fontSize: 7,
                      fontFamily: "var(--mono)", background: "var(--honey-light)",
                      color: "var(--honey-dark)", whiteSpace: "nowrap",
                    }}>
                      {m.assigned_agents[0]}
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ flex: 1, height: 5, background: "var(--rule)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${m.progress * 100}%`, background: "var(--accent)", borderRadius: 3, transition: "width 0.3s" }} />
                  </div>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--pencil)", flexShrink: 0 }}>
                    {Math.round(m.progress * 100)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontFamily: "var(--hand)", fontSize: 18, fontWeight: 700, marginBottom: 8 }}>System Health</div>
          <div className="card" style={{ padding: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <StatusDot status={health?.status === "ok" ? "connected" : "error"} pulse={health?.status === "ok"} />
              <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: health?.status === "ok" ? "#5a9a4a" : "#c4452a", fontWeight: 600 }}>
                {health?.status === "ok" ? "Connected" : "Disconnected"}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginLeft: "auto" }}>
                v{health?.version ?? "\u2014"}
              </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 14 }}>
              {[
                { label: "Status", value: health?.status ?? "\u2014" },
                { label: "Uptime", value: health ? formatUptime(health.uptime_seconds) : "\u2014" },
                { label: "Version", value: health?.version ?? "\u2014" },
              ].map((stat) => (
                <div key={stat.label} style={{ textAlign: "center", padding: "6px 4px", border: "1px solid var(--rule)", borderRadius: 4 }}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 7, color: "var(--pencil)", textTransform: "uppercase" }}>{stat.label}</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink)", marginTop: 2 }}>{stat.value}</div>
                </div>
              ))}
            </div>

            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", textTransform: "uppercase", marginBottom: 6 }}>Provider Quotas</div>
            {quotas.length === 0 && (
              <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)" }}>No quota data available</div>
            )}
            {quotas.map((q, i) => {
              const pct = q.usage_pct ?? 0;
              return (
                <div key={q.provider} style={{ marginBottom: 7 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--ink)" }}>{q.provider}</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--pencil)" }}>
                      {Math.round(pct * 100)}%
                    </span>
                  </div>
                  <div style={{ height: 5, background: "var(--rule)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${pct * 100}%`, background: QUOTA_COLORS[i % QUOTA_COLORS.length], borderRadius: 3, transition: "width 0.3s" }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {selectedAgent && (
        <div style={{
          position: "fixed", top: 0, right: 0, bottom: 0, width: 360,
          background: "var(--paper)", borderLeft: "1.5px solid var(--rule)",
          zIndex: 100, overflow: "auto", padding: 16,
          boxShadow: "-4px 0 16px rgba(0,0,0,0.1)",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 22 }}>{ROLE_ICONS[agentRole(selectedAgent)]}</span>
              <h2 style={{ fontFamily: "var(--hand)", fontSize: 20, fontWeight: 700, margin: 0 }}>{selectedAgent.name}</h2>
            </div>
            <button onClick={() => setSelectedAgent(null)} style={{ background: "none", border: "none", fontSize: 16, cursor: "pointer", color: "var(--pencil)" }}>
              \u2715
            </button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 12 }}>
            <div className="stat-card">
              <div className="label">Model</div>
              <div className="value" style={{ fontSize: 11 }}>{selectedAgent.model}</div>
            </div>
            <div className="stat-card">
              <div className="label">Status</div>
              <div className="value" style={{ fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
                <StatusDot status={AGENT_STATUS_MAP[selectedAgent.status]} pulse={selectedAgent.status === "busy"} />
                {selectedAgent.status}
              </div>
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", textTransform: "uppercase", marginBottom: 4 }}>Role</div>
            <span style={{
              padding: "2px 10px", borderRadius: 3, fontSize: 9,
              fontFamily: "var(--mono)", fontWeight: 600, textTransform: "capitalize",
              background: `${ROLE_COLORS[agentRole(selectedAgent)]}18`,
              color: ROLE_COLORS[agentRole(selectedAgent)],
              border: `1px solid ${ROLE_COLORS[agentRole(selectedAgent)]}44`,
            }}>
              {agentRole(selectedAgent)}
            </span>
          </div>
          {selectedAgent.description && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", textTransform: "uppercase", marginBottom: 4 }}>Description</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink)", lineHeight: 1.5 }}>{selectedAgent.description}</div>
            </div>
          )}
          {selectedAgent.capabilities.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", textTransform: "uppercase", marginBottom: 4 }}>Capabilities</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {selectedAgent.capabilities.map((c) => (
                  <span key={c} style={{
                    padding: "2px 8px", borderRadius: 3, fontSize: 8,
                    fontFamily: "var(--mono)", background: "var(--honey-light)",
                    color: "var(--honey-dark)",
                  }}>
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div style={{ marginTop: 14, display: "flex", gap: 6 }}>
            <button
              onClick={() => navigate("/agents")}
              style={{
                padding: "6px 14px", borderRadius: 4, cursor: "pointer",
                fontFamily: "var(--mono)", fontSize: 10,
                border: "1.3px solid var(--accent)", background: "var(--accent)",
                color: "var(--paper)",
              }}
            >
              View in Agents \u2192
            </button>
            <button
              onClick={() => setSelectedAgent(null)}
              style={{
                padding: "6px 14px", borderRadius: 4, cursor: "pointer",
                fontFamily: "var(--mono)", fontSize: 10,
                border: "1.3px solid var(--rule)", background: "var(--paper)",
                color: "var(--ink)",
              }}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
