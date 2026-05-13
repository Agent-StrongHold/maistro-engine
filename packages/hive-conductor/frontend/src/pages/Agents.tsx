import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type Agent = { id: string; name: string; model: string; status: string };

export default function Agents() {
  const [rows, setRows] = useState<Agent[]>([]);
  const load = useCallback(async () => {
    setRows(await apiGet<Agent[]>("/v1/agents"));
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      void load().catch(() => setRows([]));
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);
  return (
    <div>
      <PageHeader title="Agents" subtitle="/v1/agents" />
      <Card>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Model</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>{r.model}</td>
                <td>
                  <span className="badge">{r.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
