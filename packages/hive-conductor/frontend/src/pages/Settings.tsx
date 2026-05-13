import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { Card, PageHeader } from "../components/shared";

type Settings = {
  api_base_url: string;
  default_model: string;
  theme: string;
  log_level: string;
};

export default function Settings() {
  const [s, setS] = useState<Settings | null>(null);
  const load = useCallback(async () => {
    setS(await apiGet<Settings>("/v1/settings"));
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      void load().catch(() => setS(null));
    }, 0);
    return () => window.clearTimeout(t);
  }, [load]);
  return (
    <div>
      <PageHeader title="Settings" subtitle="/v1/settings (read-only view in phase 1)" />
      <Card>
        {s ? (
          <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(s, null, 2)}</pre>
        ) : (
          <p className="muted">Could not load settings.</p>
        )}
      </Card>
    </div>
  );
}
