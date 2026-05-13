import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type Schedule = { id: string; name: string; cron_expression: string; enabled: boolean };

export default function Schedules() {
  const [rows, setRows] = useState<Schedule[]>([]);
  const load = useCallback(async () => {
    setRows(await apiGet<Schedule[]>("/v1/schedules"));
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      void load().catch(() => setRows([]));
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);
  return (
    <div>
      <PageHeader title="Schedules" subtitle="/v1/schedules" />
      <Card>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Cron</th>
              <th>On</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>
                  <code>{r.cron_expression}</code>
                </td>
                <td>{r.enabled ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
