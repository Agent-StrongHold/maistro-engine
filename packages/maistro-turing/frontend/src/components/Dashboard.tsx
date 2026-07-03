import { useEffect, useState } from "react";
import { api, type Snapshot } from "@/lib/api";

function Meter({ label, value, max = 1 }: { label: string; value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div style={{ marginBottom: "0.75rem" }}>
      <div className="meter-label">
        <span>{label}</span>
        <span>{value.toFixed(2)}</span>
      </div>
      <div className="meter">
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      api
        .snapshot()
        .then((s) => live && setSnap(s))
        .catch((e) => live && setErr(String(e)));
    load();
    const t = setInterval(load, 5000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  if (err) return <p className="err">{err} — are you logged in?</p>;
  if (!snap) return <p className="muted">loading live state…</p>;

  return (
    <>
      <div className="card">
        <strong>mood</strong>
        <div style={{ marginTop: "0.75rem" }}>
          <Meter label="valence" value={(snap.mood.valence + 1) / 2} />
          <Meter label="arousal" value={snap.mood.arousal} />
          <Meter label="focus" value={snap.mood.focus} />
        </div>
      </div>

      <div className="card">
        <strong>drives</strong>
        <div style={{ marginTop: "0.75rem" }}>
          <Meter label="creative urge" value={snap.drives.creative_urge} />
          <Meter label="curiosity" value={snap.drives.curiosity} />
          <Meter label="diligence" value={snap.drives.diligence} />
          <Meter label="restlessness" value={snap.drives.restlessness} />
        </div>
      </div>

      <strong style={{ fontFamily: "var(--mono)" }}>personality · HEXACO</strong>
      <div className="grid" style={{ marginTop: "0.75rem" }}>
        {Object.entries(snap.personality).map(([trait, facets]) => (
          <div className="card" key={trait}>
            <div className="kind-tag">{trait.replace(/_/g, " ")}</div>
            <div style={{ marginTop: "0.75rem" }}>
              {Object.entries(facets).map(([facet, score]) => (
                <Meter key={facet} label={facet} value={score} max={5} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
