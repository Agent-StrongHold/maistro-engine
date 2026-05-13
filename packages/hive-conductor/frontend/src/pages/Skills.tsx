import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type Skill = { id: string; name: string; version: string; category: string; enabled: boolean };

export default function Skills() {
  const [rows, setRows] = useState<Skill[]>([]);
  const load = useCallback(async () => {
    setRows(await apiGet<Skill[]>("/v1/skills"));
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      void load().catch(() => setRows([]));
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);
  return (
    <div>
      <PageHeader title="Skills" subtitle="/v1/skills" />
      <Card>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Version</th>
              <th>Category</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>{r.version}</td>
                <td>{r.category}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
