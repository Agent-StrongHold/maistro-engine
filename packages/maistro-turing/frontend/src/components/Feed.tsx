import { useEffect, useState } from "react";
import { api, type Artifact } from "@/lib/api";

const KINDS = ["", "blog", "reflection", "curiosity", "emotion"];

export default function Feed() {
  const [items, setItems] = useState<Artifact[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [kind, setKind] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const limit = 20;

  useEffect(() => {
    api
      .feed(offset, limit, kind || undefined)
      .then((p) => {
        setItems(p.items);
        setTotal(p.total);
      })
      .catch((e) => setErr(String(e)));
  }, [offset, kind]);

  if (err) return <p className="err">{err}</p>;

  return (
    <>
      <div style={{ display: "flex", gap: "0.4rem", marginBottom: "1rem" }}>
        {KINDS.map((k) => (
          <button
            key={k || "all"}
            onClick={() => {
              setKind(k);
              setOffset(0);
            }}
            style={{ opacity: kind === k ? 1 : 0.55 }}
          >
            {k || "all"}
          </button>
        ))}
      </div>

      {items.length === 0 && <p className="muted">no artifacts yet.</p>}

      {items.map((a) => (
        <a className="card" key={a.artifact_id} href={`/feed/${a.artifact_id}`} style={{ display: "block" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span className="kind-tag">{a.kind}</span>
            <span className="muted" style={{ fontFamily: "var(--mono)", fontSize: "0.75rem" }}>
              {new Date(a.created_at).toLocaleString()}
            </span>
          </div>
          <h3 style={{ margin: "0.6rem 0 0.3rem" }}>{a.title}</h3>
          <p className="muted" style={{ margin: 0 }}>
            {a.body.slice(0, 160)}
            {a.body.length > 160 ? "…" : ""}
          </p>
        </a>
      ))}

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
          ← prev
        </button>
        <span className="muted" style={{ fontFamily: "var(--mono)", alignSelf: "center" }}>
          {offset + 1}–{Math.min(offset + limit, total)} of {total}
        </span>
        <button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>
          next →
        </button>
      </div>
    </>
  );
}
