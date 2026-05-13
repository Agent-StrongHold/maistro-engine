import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type Session = { id: string; title: string; message_count: number; updated_at: string };

export default function Chat() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setErr(null);
      const data = await apiGet<Session[]>("/v1/chat/sessions");
      setSessions(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "load failed");
    }
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Chat"
        subtitle="Sessions from /v1/chat (stub)."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => void load()}>
            Refresh
          </button>
        }
      />
      {err ? <p className="muted">{err}</p> : null}
      <div className="grid-2">
        <Card>
          <h3 className="muted" style={{ marginTop: 0 }}>
            Sessions
          </h3>
          <ul style={{ paddingLeft: "1.1rem", margin: 0 }}>
            {sessions.map((s) => (
              <li key={s.id}>
                <strong>{s.title}</strong>{" "}
                <span className="muted">
                  ({s.message_count}) {s.id.slice(0, 8)}…
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h3 className="muted" style={{ marginTop: 0 }}>
            Quick action
          </h3>
          <button
            type="button"
            className="btn"
            onClick={() =>
              void (async () => {
                const s = await apiPost<{ id: string }>("/v1/chat/sessions", { title: "New from UI" });
                await apiPost(`/v1/chat/sessions/${s.id}/messages`, {
                  role: "user",
                  content: "Hello from Hive UI",
                });
                void load();
              })()
            }
          >
            New session + message
          </button>
        </Card>
      </div>
    </div>
  );
}
