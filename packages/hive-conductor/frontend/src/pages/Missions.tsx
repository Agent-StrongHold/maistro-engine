import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type Mission = {
  id: string;
  name: string;
  status: string;
  progress: number;
  steps_completed: number;
  steps_total: number;
};

export default function Missions() {
  const [rows, setRows] = useState<Mission[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setErr(null);
      setRows(await apiGet<Mission[]>("/v1/tasks"));
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
        title="Missions"
        subtitle="Hive /v1/tasks — missions, not maistro-core /tasks."
        actions={
          <button type="button" className="btn" onClick={() => void load()}>
            Refresh
          </button>
        }
      />
      {err ? <p className="muted">{err}</p> : null}
      <Card>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Steps</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td>{m.name}</td>
                <td>
                  <span className="badge">{m.status}</span>
                </td>
                <td>{Math.round(m.progress * 100)}%</td>
                <td>
                  {m.steps_completed}/{m.steps_total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
