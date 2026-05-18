import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Hex } from "../components/shared";

type Skill = {
  id: string; name: string; description: string; version: string; category: string;
  author: string; enabled: boolean; usage_count: number; avg_latency_ms: number;
  success_rate: number; tags: string[];
  parameters: { name: string; type: string; required: boolean }[];
};

export default function Skills() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [sel, setSel] = useState<Skill | null>(null);
  const load = useCallback(async () => { try { setSkills(await apiGet<Skill[]>("/v1/skills")); } catch { /* */ } }, []);
  useEffect(() => { const t = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(t); }, [load]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: sel ? "300px 1fr" : "1fr", gap: 0, minHeight: "calc(100vh - 60px)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
          <h1 style={{ fontFamily: "var(--hand)", fontSize: 24, fontWeight: 600, margin: 0 }}>Skills</h1>
          <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)" }}>{skills.length} installed</span>
        </div>
        {skills.map((s) => (
          <div key={s.id} className="card" onClick={() => setSel(s)} style={{ cursor: "pointer", opacity: s.enabled ? 1 : 0.6, borderColor: sel?.id === s.id ? "var(--accent)" : undefined }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 8, alignItems: "center" }}>
              <div>
                <div style={{ fontFamily: "var(--hand)", fontSize: 15 }}>{s.name}</div>
                <div style={{ fontFamily: "var(--hand)", fontSize: 11, color: "var(--pencil)" }}>{s.description}</div>
              </div>
              <Hex variant={s.enabled ? "ok" : "muted"}>{s.enabled ? "on" : "off"}</Hex>
              <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)" }}>{s.usage_count}x</span>
            </div>
            <div style={{ display: "flex", gap: 4, marginTop: 5 }}>
              <Hex variant="accent">{s.category}</Hex>
              {s.tags.map((t) => <Hex key={t} variant="muted">{t}</Hex>)}
            </div>
          </div>
        ))}
      </div>

      {sel && (
        <div style={{ padding: "0 0 0 18px", borderLeft: "1.5px dashed var(--pencil)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h2 style={{ fontFamily: "var(--hand)", fontSize: 22, fontWeight: 600, margin: "0 0 8px" }}>{sel.name}</h2>
            <span className="btn" style={{ fontSize: 9, padding: "2px 8px" }} onClick={() => setSel(null)}>close</span>
          </div>
          <div style={{ fontFamily: "var(--hand)", fontSize: 14, color: "var(--pencil)", marginBottom: 14 }}>{sel.description}</div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8, marginBottom: 14 }}>
            {[
              { label: "VERSION", val: sel.version },
              { label: "AUTHOR", val: sel.author },
              { label: "USAGE", val: `${sel.usage_count}x` },
              { label: "AVG LATENCY", val: `${Math.round(sel.avg_latency_ms)}ms` },
              { label: "SUCCESS RATE", val: `${(sel.success_rate * 100).toFixed(0)}%` },
              { label: "PARAMS", val: `${sel.parameters.length}` },
            ].map((s) => (
              <div key={s.label} style={{ textAlign: "center", padding: "8px 6px", border: "1.3px solid var(--rule)", borderRadius: 5 }}>
                <div style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--pencil)" }}>{s.label}</div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--ink)", marginTop: 2 }}>{s.val}</div>
              </div>
            ))}
          </div>

          <div style={{ marginBottom: 14 }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginBottom: 4 }}>SUCCESS RATE</div>
            <div className="progress-bar" style={{ height: 8 }}>
              <div className="progress-bar-fill" style={{ width: `${sel.success_rate * 100}%`, background: sel.success_rate > 0.9 ? "var(--ok)" : sel.success_rate > 0.7 ? "var(--accent)" : "var(--danger)" }} />
            </div>
          </div>

          {sel.parameters.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginBottom: 4 }}>PARAMETERS</div>
              <div className="card" style={{ padding: 0 }}>
                <table className="table">
                  <thead><tr><th>Name</th><th>Type</th><th>Required</th></tr></thead>
                  <tbody>
                    {sel.parameters.map((p) => (
                      <tr key={p.name}>
                        <td style={{ color: "var(--accent)" }}>{p.name}</td>
                        <td style={{ color: "var(--pencil)" }}>{p.type}</td>
                        <td style={{ color: p.required ? "var(--danger)" : "var(--pencil)" }}>{p.required ? "required" : "optional"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            <Hex variant="muted">id: {sel.id}</Hex>
            <Hex variant="muted">author: {sel.author}</Hex>
            <Hex variant="accent">{sel.category}</Hex>
            {sel.tags.map((t) => <Hex key={t} variant="muted">{t}</Hex>)}
          </div>
        </div>
      )}
    </div>
  );
}
