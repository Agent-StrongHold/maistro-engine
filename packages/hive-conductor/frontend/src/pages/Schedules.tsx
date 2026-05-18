import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, apiPatch, apiDelete } from "../lib/api";
import { Hex, StatCard } from "../components/shared";

type Schedule = {
  id: string; name: string; description: string; cron_expression: string;
  mission_template_id: string | null; enabled: boolean;
  last_run: string | null; next_run: string | null;
  created_at: string; updated_at: string;
};

export default function Schedules() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [tab, setTab] = useState<"schedules" | "history">("schedules");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newCron, setNewCron] = useState("0 * * * *");
  const load = useCallback(async () => { try { setSchedules(await apiGet<Schedule[]>("/v1/schedules")); } catch { /* */ } }, []);
  useEffect(() => { void load(); }, [load]);

  async function createSchedule() {
    if (!newName.trim()) return;
    try {
      await apiPost<Schedule>("/v1/schedules", { name: newName.trim(), description: newDesc.trim(), cron_expression: newCron, enabled: true });
      setCreating(false);
      setNewName("");
      setNewDesc("");
      setNewCron("0 * * * *");
      await load();
    } catch { /* */ }
  }

  async function toggleSchedule(s: Schedule) {
    try {
      await apiPatch<Schedule>(`/v1/schedules/${s.id}`, { enabled: !s.enabled });
      await load();
    } catch { /* */ }
  }

  async function deleteSchedule(id: string) {
    try { await apiDelete(`/v1/schedules/${id}`); await load(); } catch { /* */ }
  }

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h1 style={{ fontFamily: "var(--hand)", fontSize: 26, fontWeight: 700, margin: 0 }}>Schedules</h1>
          <button className="btn" style={{ fontSize: 9, padding: "2px 8px" }} onClick={() => setCreating(true)}>+ new</button>
        </div>
        <div style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--rule)", marginBottom: -8 }}>
          {(["schedules", "history"] as const).map((t) => (
            <div key={t} onClick={() => setTab(t)} style={{ padding: "7px 16px", fontFamily: "var(--mono)", fontSize: 10, cursor: "pointer", borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent", color: tab === t ? "var(--ink)" : "var(--pencil)", textTransform: "capitalize" }}>{t}</div>
          ))}
        </div>
      </div>

      {tab === "schedules" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14 }}>
          {creating && (
            <div className="card" style={{ borderLeft: "3px solid var(--accent)" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <input className="input-field" placeholder="schedule name" value={newName} onChange={(e) => setNewName(e.target.value)} autoFocus />
                <input className="input-field" placeholder="description" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)" }}>CRON</span>
                  <input className="input-field" style={{ flex: 1, fontFamily: "var(--mono)" }} value={newCron} onChange={(e) => setNewCron(e.target.value)} />
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                  <button className="btn btn-accent" style={{ fontSize: 9, padding: "2px 10px" }} onClick={() => void createSchedule()} disabled={!newName.trim()}>create</button>
                  <button className="btn" style={{ fontSize: 9, padding: "2px 10px" }} onClick={() => setCreating(false)}>cancel</button>
                </div>
              </div>
            </div>
          )}

          {schedules.map((s) => (
            <div key={s.id} className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "var(--hand)", fontSize: 17, fontWeight: 600 }}>{s.name}</div>
                  <div style={{ fontFamily: "var(--hand)", fontSize: 12, color: "var(--pencil)", margin: "2px 0 4px" }}>{s.description}</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent)", fontWeight: 600 }}>{s.cron_expression}</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 6, marginTop: 8 }}>
                    <StatCard label="Last Run" value={s.last_run ? new Date(s.last_run).toLocaleString() : "never"} />
                    <StatCard label="Next Run" value={s.next_run ? new Date(s.next_run).toLocaleString() : "pending"} />
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6, marginLeft: 12 }}>
                  <div className={`toggle${s.enabled ? " on" : ""}`} onClick={() => void toggleSchedule(s)} style={{ cursor: "pointer" }} />
                  <Hex variant={s.enabled ? "ok" : "muted"}>{s.enabled ? "active" : "off"}</Hex>
                  <button className="btn" style={{ fontSize: 8, padding: "1px 6px", borderColor: "var(--danger)", color: "var(--danger)", opacity: 0.5 }} onClick={() => void deleteSchedule(s.id)}>delete</button>
                </div>
              </div>
            </div>
          ))}
          {schedules.length === 0 && !creating && <div style={{ fontFamily: "var(--hand)", fontSize: 16, color: "var(--pencil)", padding: 20 }}>no schedules configured</div>}
        </div>
      )}

      {tab === "history" && (
        <div style={{ marginTop: 14, fontFamily: "var(--hand)", fontSize: 14, color: "var(--pencil)", padding: 20 }}>
          execution history will appear here when runs complete
        </div>
      )}
    </div>
  );
}
