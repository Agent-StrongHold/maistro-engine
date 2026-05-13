import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type Server = { id: string; name: string; status: string; tools_count: number };
type Tool = { id: string; name: string; server_id: string };

export default function MCP() {
  const [servers, setServers] = useState<Server[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [scanDone, setScanDone] = useState(false);

  const load = useCallback(async () => {
    const [s, t] = await Promise.all([
      apiGet<Server[]>("/v1/mcp/servers"),
      apiGet<Tool[]>("/v1/mcp/tools"),
    ]);
    setServers(s);
    setTools(t);
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => {
      void load().catch(() => {
        setServers([]);
        setTools([]);
      });
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);

  useEffect(() => {
    let inner = 0;
    const outer = window.setTimeout(() => {
      setScanDone(false);
      inner = window.setTimeout(() => setScanDone(true), 400);
    }, 0);
    return () => {
      window.clearTimeout(outer);
      if (inner) window.clearTimeout(inner);
    };
  }, [servers.length, tools.length]);

  return (
    <div>
      <PageHeader
        title="MCP"
        subtitle={scanDone ? "Scan complete (stub timer)." : "Scanning…"}
        actions={
          <button type="button" className="btn" onClick={() => void load()}>
            Refresh
          </button>
        }
      />
      <div className="grid-2">
        <Card>
          <h3 className="muted" style={{ marginTop: 0 }}>
            Servers
          </h3>
          <ul>
            {servers.map((s) => (
              <li key={s.id}>
                {s.name} — <span className="badge">{s.status}</span> ({s.tools_count} tools)
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h3 className="muted" style={{ marginTop: 0 }}>
            Tools
          </h3>
          <ul>
            {tools.map((t) => (
              <li key={t.id}>
                <code>{t.name}</code> <span className="muted">({t.server_id})</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
