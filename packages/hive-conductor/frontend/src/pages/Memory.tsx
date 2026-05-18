import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, apiDelete } from "../lib/api";
import { Hex, StatCard } from "../components/shared";

type Entry = {
  id: string; key: string; value: string; namespace: string;
  tags: string[]; embedding: string | null;
  created_at: string; updated_at: string;
  accessed_count: number; ttl_seconds: number | null;
};

export default function Memory() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [sel, setSel] = useState<Entry | null>(null);
  const [filter, setFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");
  const [newNs, setNewNs] = useState("general");
  const load = useCallback(async () => { try { setEntries(await apiGet<Entry[]>("/v1/memory/entries")); } catch { /* */ } }, []);
  useEffect(() => { void load(); }, [load]);

  async function createEntry() {
    if (!newKey.trim()) return;
    try {
      await apiPost("/v1/memory/entries", { key: newKey.trim(), value: newVal, namespace: newNs, tags: [] });
      setCreating(false);
      setNewKey("");
      setNewVal("");
      await load();
    } catch { /* */ }
  }

  async function deleteEntry(id: string) {
    try { await apiDelete(`/v1/memory/entries/${id}`); setSel(null); await load(); } catch { /* */ }
  }

  const namespaces = [...new Set(entries.map((e) => e.namespace))];
  const filtered = filter ? entries.filter((e) => e.namespace === filter) : entries;

  return (
    <div style={{ display: "grid", gridTemplateColumns: sel ? "1fr 320px" : "1fr", gap: 0, minHeight: "calc(100vh - 60px)" }}>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <h1 style={{ fontFamily: "var(--hand)", fontSize: 26, fontWeight: 700, margin: 0 }}>Memory</h1>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)" }}>{entries.length} entries</span>
            <button className="btn" style={{ fontSize: 9, padding: "2px 8px" }} onClick={() => setCreating(true)}>+ new</button>
          </div>
        </div>

        {creating && (
          <div className="card" style={{ borderLeft: "3px solid var(--accent)", marginBottom: 10 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
              <input className="input-field" placeholder="key" value={newKey} onChange={(e) => setNewKey(e.target.value)} autoFocus style={{ flex: 1 }} />
              <input className="input-field" placeholder="namespace" value={newNs} onChange={(e) => setNewNs(e.target.value)} style={{ width: 100 }} />
            </div>
            <textarea className="input-field" placeholder="value" value={newVal} onChange={(e) => setNewVal(e.target.value)} rows={2} style={{ resize: "vertical" }} />
            <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
              <button className="btn btn-accent" style={{ fontSize: 9, padding: "2px 10px" }} onClick={() => void createEntry()} disabled={!newKey.trim()}>save</button>
              <button className="btn" style={{ fontSize: 9, padding: "2px 10px" }} onClick={() => setCreating(false)}>cancel</button>
            </div>
          </div>
        )}

        <div style={{ display: "flex", gap: 4, marginBottom: 10, flexWrap: "wrap" }}>
          <span className={`hex-badge${!filter ? " hex-badge-ok" : ""}`} style={{ cursor: "pointer" }} onClick={() => setFilter("")}>all ({entries.length})</span>
          {namespaces.map((ns) => (
            <span key={ns} className={`hex-badge${filter === ns ? " hex-badge-ok" : ""}`} style={{ cursor: "pointer" }} onClick={() => setFilter(ns)}>
              {ns} ({entries.filter((e) => e.namespace === ns).length})
            </span>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {filtered.map((e) => (
            <div key={e.id} className="card" onClick={() => setSel(e)} style={{ cursor: "pointer", borderColor: sel?.id === e.id ? "var(--accent)" : undefined }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, alignItems: "center" }}>
                <div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--accent)" }}>{e.key}</div>
                  <div style={{ fontFamily: "var(--hand)", fontSize: 12, color: "var(--pencil)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.value}</div>
                </div>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  <Hex variant="muted">{e.namespace}</Hex>
                  {e.embedding ? <Hex variant="ok">embedded</Hex> : null}
                </div>
              </div>
              {e.tags.length > 0 && (
                <div style={{ display: "flex", gap: 3, marginTop: 4 }}>
                  {e.tags.map((t) => <Hex key={t} variant="">{t}</Hex>)}
                </div>
              )}
            </div>
          ))}
          {filtered.length === 0 && <div style={{ fontFamily: "var(--hand)", fontSize: 16, color: "var(--pencil)", padding: 20 }}>no entries</div>}
        </div>
      </div>

      {sel && (
        <div style={{ padding: "0 0 0 14px", borderLeft: "1.5px dashed var(--honey)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h2 style={{ fontFamily: "var(--hand)", fontSize: 20, fontWeight: 700, margin: 0, wordBreak: "break-all" }}>{sel.key}</h2>
            <div style={{ display: "flex", gap: 4 }}>
              <button className="btn" style={{ fontSize: 9, padding: "2px 8px", borderColor: "var(--danger)", color: "var(--danger)" }} onClick={() => void deleteEntry(sel.id)}>delete</button>
              <span className="btn" style={{ fontSize: 9, padding: "2px 8px" }} onClick={() => setSel(null)}>close</span>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, margin: "10px 0" }}>
            <StatCard label="Namespace" value={sel.namespace} />
            <StatCard label="Accessed" value={`${sel.accessed_count}x`} />
            <StatCard label="TTL" value={sel.ttl_seconds ? `${sel.ttl_seconds}s` : "none"} />
            <StatCard label="Embedding" value={sel.embedding ? "yes" : "no"} />
            <StatCard label="Created" value={new Date(sel.created_at).toLocaleDateString()} />
            <StatCard label="Updated" value={new Date(sel.updated_at).toLocaleDateString()} />
          </div>

          <div style={{ marginBottom: 10 }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginBottom: 4, textTransform: "uppercase" }}>Value</div>
            <div style={{ padding: "8px 10px", background: "rgba(0,0,0,0.03)", borderRadius: 4, border: "1px solid var(--rule)", fontFamily: "var(--mono)", fontSize: 10, whiteSpace: "pre-wrap", wordBreak: "break-all", maxHeight: 200, overflow: "auto" }}>
              {sel.value}
            </div>
          </div>

          {sel.tags.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginBottom: 4, textTransform: "uppercase" }}>Tags</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {sel.tags.map((t) => <Hex key={t}>{t}</Hex>)}
              </div>
            </div>
          )}

          <div style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--pencil)" }}>id: {sel.id}</div>
        </div>
      )}
    </div>
  );
}
