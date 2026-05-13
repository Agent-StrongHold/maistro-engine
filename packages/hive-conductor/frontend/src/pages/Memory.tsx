import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type Entry = { id: string; key: string; namespace: string; value: string };

export default function Memory() {
  const [rows, setRows] = useState<Entry[]>([]);
  const load = useCallback(async () => {
    setRows(await apiGet<Entry[]>("/v1/memory/entries"));
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      void load().catch(() => setRows([]));
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);
  return (
    <div>
      <PageHeader title="Memory" subtitle="/v1/memory/entries" />
      <Card>
        <table className="table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Namespace</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <code>{r.key}</code>
                </td>
                <td>{r.namespace}</td>
                <td>{r.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
