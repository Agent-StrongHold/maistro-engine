import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface SelfModel {
  mood: { valence: number; arousal: number; focus: number };
  facets: Record<string, number>;
}

export default function Admin() {
  const [model, setModel] = useState<SelfModel | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function load() {
    try {
      const res = await fetch(`${(import.meta as any).env.PUBLIC_TURING_API}/v1/admin/self-model`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
      setModel(await res.json());
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function saveMood(field: "valence" | "arousal" | "focus", value: number) {
    try {
      await api.patchMood({ [field]: value });
      setStatus(`mood.${field} = ${value}`);
      load();
    } catch (e) {
      setErr(String(e));
    }
  }

  async function saveFacet(facet: string, value: number) {
    try {
      await api.patchFacet(facet, value);
      setStatus(`facet ${facet} = ${value}`);
    } catch (e) {
      setErr(String(e));
    }
  }

  if (err) return <p className="err">{err} — admin role required.</p>;
  if (!model) return <p className="muted">loading…</p>;

  return (
    <>
      {status && <p style={{ color: "var(--accent)", fontFamily: "var(--mono)" }}>{status}</p>}

      <div className="card">
        <strong>mood</strong>
        {(["valence", "arousal", "focus"] as const).map((f) => (
          <div key={f} style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.6rem" }}>
            <label className="muted" style={{ width: 80, fontFamily: "var(--mono)" }}>
              {f}
            </label>
            <input
              type="range"
              min={f === "valence" ? -1 : 0}
              max={1}
              step={0.05}
              defaultValue={model.mood[f]}
              onMouseUp={(e) => saveMood(f, parseFloat((e.target as HTMLInputElement).value))}
            />
            <span className="muted">{model.mood[f].toFixed(2)}</span>
          </div>
        ))}
      </div>

      <div className="card">
        <strong>personality facets</strong>
        <div className="grid" style={{ marginTop: "0.75rem" }}>
          {Object.entries(model.facets).map(([facet, score]) => (
            <div key={facet} style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              <label className="muted" style={{ fontFamily: "var(--mono)", fontSize: "0.78rem" }}>
                {facet}
              </label>
              <input
                type="range"
                min={1}
                max={5}
                step={0.1}
                defaultValue={score}
                onMouseUp={(e) => saveFacet(facet, parseFloat((e.target as HTMLInputElement).value))}
              />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
