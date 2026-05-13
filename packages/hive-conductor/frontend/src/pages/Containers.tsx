import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type C = { id: string; name: string; image: string; status: string; cpu_usage: number };

export default function Containers() {
  const [rows, setRows] = useState<C[]>([]);
  const load = useCallback(async () => {
    setRows(await apiGet<C[]>("/v1/containers"));
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      void load().catch(() => setRows([]));
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);
  return (
    <div>
      <PageHeader title="Containers" subtitle="/v1/containers" />
      <Card>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Image</th>
              <th>Status</th>
              <th>CPU %</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>
                  <code>{r.image}</code>
                </td>
                <td>
                  <span className="badge">{r.status}</span>
                </td>
                <td>{r.cpu_usage.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
