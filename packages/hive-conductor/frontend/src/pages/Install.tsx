import { useState } from "react";

const defaultBody = `{
  "schema_version": "1",
  "features": ["core_lib", "server"],
  "compose_addons": [],
  "stack_bringup": "none",
  "llm_gateway": "litellm",
  "observability_backend": "none",
  "deployment_tier": "local_docker",
  "container_runtime": "auto",
  "users_intent": "skip",
  "provider_accounts": {}
}`;

export default function Install() {
  const [input, setInput] = useState(defaultBody);
  const [out, setOut] = useState<string>("");
  const [err, setErr] = useState<string>("");
  const [loading, setLoading] = useState(false);

  async function loadSessionDefaults() {
    setErr("");
    setLoading(true);
    try {
      const res = await fetch("/v1/install/session");
      const text = await res.text();
      if (!res.ok) {
        setErr(`${res.status}: ${text}`);
        return;
      }
      const data = JSON.parse(text) as { defaults?: Record<string, unknown> };
      setInput(JSON.stringify(data.defaults ?? {}, null, 2));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function validateSession() {
    setErr("");
    setOut("");
    setLoading(true);
    try {
      const body = JSON.parse(input) as Record<string, unknown>;
      const res = await fetch("/v1/install/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) {
        setErr(`${res.status}: ${text}`);
        return;
      }
      setOut(JSON.stringify(JSON.parse(text), null, 2));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function runPlan() {
    setErr("");
    setOut("");
    setLoading(true);
    try {
      const body = JSON.parse(input) as Record<string, unknown>;
      const res = await fetch("/v1/install/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) {
        setErr(`${res.status}: ${text}`);
        return;
      }
      setOut(JSON.stringify(JSON.parse(text), null, 2));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page install-page">
      <header className="page-header">
        <h1>Install plan</h1>
        <p className="muted">
          Use <code>GET /v1/install/session</code> for defaults, <code>POST /v1/install/session</code> to merge
          partial JSON, and <code>POST /v1/install/plan</code> for the full plan (same as{" "}
          <code>maistro-install --json</code>). Requires monorepo layout for{" "}
          <code>maistro-bootstrap</code>.
        </p>
      </header>
      <div className="install-grid">
        <label className="field">
          <span>Answers JSON</span>
          <textarea
            className="install-textarea"
            rows={16}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            spellCheck={false}
          />
        </label>
        <div className="install-actions">
          <button type="button" className="btn" disabled={loading} onClick={() => void loadSessionDefaults()}>
            GET /v1/install/session
          </button>
          <button type="button" className="btn" disabled={loading} onClick={() => void validateSession()}>
            POST /v1/install/session
          </button>
          <button type="button" className="btn btn-primary" disabled={loading} onClick={() => void runPlan()}>
            {loading ? "Working…" : "POST /v1/install/plan"}
          </button>
          {err ? <pre className="install-error">{err}</pre> : null}
        </div>
        {out ? (
          <label className="field full-width">
            <span>Response JSON</span>
            <textarea className="install-textarea" rows={24} value={out} readOnly spellCheck={false} />
          </label>
        ) : null}
      </div>
    </div>
  );
}
