import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type CliSession = { id: string; cwd: string };

export default function CLI() {
  const [rows, setRows] = useState<CliSession[]>([]);
  const load = useCallback(async () => {
    setRows(await apiGet<CliSession[]>("/v1/cli/sessions"));
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      void load().catch(() => setRows([]));
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);
  return (
    <div>
      <PageHeader
        title="CLI"
        subtitle="/v1/cli/sessions"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() =>
              void (async () => {
                await apiPost("/v1/cli/sessions");
                void load();
              })()
            }
          >
            New session
          </button>
        }
      />
      <Card>
        <ul>
          {rows.map((r) => (
            <li key={r.id}>
              <code>{r.id}</code> cwd {r.cwd}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
