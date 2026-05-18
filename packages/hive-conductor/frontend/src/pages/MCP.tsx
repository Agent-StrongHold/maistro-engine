import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Hex, StatCard } from "../components/shared";

type Server = {
  id: string; name: string; description: string; url: string;
  status: string; tools_count: number; last_ping: string | null;
  version: string | null; capabilities: string[];
};

type Tool = {
  id: string; server_id: string; name: string; description: string;
  input_schema: Record<string, unknown>; category: string | null;
};

export default function MCP() {
  const [servers, setServers] = useState<Server[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [sel, setSel] = useState<Server | null>(null);
  const [tab, setTab] = useState<"servers" | "tools">("servers");

  const load = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([apiGet<Server[]>("/v1/mcp/servers"), apiGet<Tool[]>("/v1/mcp/tools")]);
      setServers(s);
      setTools(t);
    } catch { /* */ }
  }, []);

  useEffect(() => { const t = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(t); }, [load]);

  return (
    <div>
      <div className="page-header">
        <h1 style={{ fontFamily: "var(--hand)", fontSize: 26, fontWeight: 700, margin: 0 }}>MCP</h1>
        <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)" }}>{servers.length} servers · {tools.length} tools</span>
      </div>

      <div style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--rule)", marginBottom: 12 }}>
        {(["servers", "tools"] as const).map((t) => (
          <div key={t} onClick={() => setTab(t)} style={{ padding: "7px 16px", fontFamily: "var(--mono)", fontSize: 10, cursor: "pointer", borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent", color: tab === t ? "var(--ink)" : "var(--pencil)", textTransform: "capitalize" }}>{t}</div>
        ))}
      </div>

      {tab === "servers" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {servers.map((s) => {
            const serverTools = tools.filter((t) => t.server_id === s.id);
            return (
              <div key={s.id} className="card" onClick={() => setSel(sel?.id === s.id ? null : s)} style={{ cursor: "pointer" }}>
                <div style={{ display: "grid", gridTemplateColumns: "12px 1fr auto auto", gap: 10, alignItems: "center" }}>
                  <div style={{ width: 10, height: 10, borderRadius: "50%", background: s.status === "connected" ? "var(--ok)" : "var(--danger)" }} />
                  <div>
                    <div style={{ fontFamily: "var(--hand)", fontSize: 15, fontWeight: 600 }}>{s.name}</div>
                    <div style={{ fontFamily: "var(--hand)", fontSize: 11, color: "var(--pencil)" }}>{s.description}</div>
                  </div>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", textAlign: "center" }}>{s.tools_count} tools</span>
                  <Hex variant={s.status === "connected" ? "ok" : "danger"}>{s.status}</Hex>
                </div>

                {sel?.id === s.id && (
                  <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px dotted var(--rule)" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 6, marginBottom: 10 }}>
                      <StatCard label="URL" value={s.url.replace("http://", "").replace("/mcp", "")} />
                      <StatCard label="Version" value={s.version ?? "—"} />
                      <StatCard label="Last Ping" value={s.last_ping ? new Date(s.last_ping).toLocaleTimeString() : "never"} />
                      <StatCard label="Tools" value={`${s.tools_count}`} />
                    </div>

                    {s.capabilities.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginBottom: 3 }}>CAPABILITIES</div>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {s.capabilities.map((c) => <Hex key={c}>{c}</Hex>)}
                        </div>
                      </div>
                    )}

                    {serverTools.length > 0 && (
                      <div>
                        <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginBottom: 3 }}>TOOLS</div>
                        {serverTools.map((t) => (
                          <div key={t.id} style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 6, padding: "4px 6px", borderBottom: "1px dotted var(--rule)" }}>
                            <div>
                              <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--accent)" }}>{t.name}</span>
                              <span style={{ fontFamily: "var(--hand)", fontSize: 10, color: "var(--pencil)", marginLeft: 8 }}>{t.description}</span>
                            </div>
                            {t.category && <Hex variant="muted">{t.category}</Hex>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
          {servers.length === 0 && <div style={{ fontFamily: "var(--hand)", fontSize: 16, color: "var(--pencil)", padding: 20 }}>no MCP servers configured</div>}
        </div>
      )}

      {tab === "tools" && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead><tr><th>Tool</th><th>Server</th><th>Category</th><th>Description</th></tr></thead>
            <tbody>
              {tools.map((t) => (
                <tr key={t.id}>
                  <td style={{ color: "var(--accent)" }}>{t.name}</td>
                  <td style={{ color: "var(--pencil)" }}>{t.server_id}</td>
                  <td>{t.category ? <Hex variant="muted">{t.category}</Hex> : "—"}</td>
                  <td style={{ color: "var(--pencil)", fontSize: 8 }}>{t.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
