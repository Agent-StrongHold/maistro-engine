# PM Fleet POC Runbook

Branch: `research/pm-fleet-poc`

**Platform context:** This repo is the `maistro-engine` sandbox template inside **Jedai Force Convergence** (`container_registry/user_containers/sandbox_templates/maistro-engine`). It is **not** the Vibe Hosting Launch app. See JFC [`docs/MAISTRO-ENGINE-IN-JFC.md`](../../../../docs/MAISTRO-ENGINE-IN-JFC.md).

`HIVE_POC_MODE=pm` is a **demo overlay** (program hyperagent, Jira drafts, trimmed nav). Default Hive mode is full multi-agent / multi-MCP engineering conductor.

Hive Conductor is the product UI (port **8101**). Maistro Engine API runs on port **8000** with PM fleet agents embedded in-process via `EngineService`.

## Quick start (local)

```bash
# Terminal 1 — maistro API
export MAISTRO_POC_MODE=pm
export API_KEYS=alice:changeme-alice,bob:changeme-bob
export REQUIRE_AUTH=false
export CORS_ORIGINS=http://localhost:8101,http://localhost:5173
PYTHONPATH=packages/maistro-server/src:packages/maistro-core/src \
  uv run uvicorn maistro_server.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Hive backend + frontend
export MAISTRO_POC_MODE=pm
export HIVE_POC_MODE=pm
export HIVE_LOG_LEVEL=debug
# PM agent invokes use stub tools (no LiteLLM). Optional: MAISTRO_DRY_RUN=1 for engineering conductor.
# Browser devtools: all /v1 calls log as [hive] when Vite dev server is running.
cd packages/hive-conductor/backend
export PYTHONPATH=../../maistro-core/src:.
uvicorn main:app --host 0.0.0.0 --port 8101

cd packages/hive-conductor/frontend && VITE_POC_MODE=pm npm run dev
```

Open Hive at the Vite dev URL (typically `http://localhost:5173`). Default route lands on **Program** (meta hyperagent + fleet).

**UI must be PM mode:** set `VITE_POC_MODE=pm` when building the frontend, or run `VITE_POC_MODE=pm npm run dev`. The backend also exposes `pm_poc_mode` on `GET /health` so the SPA can switch nav even if the build flag was missed. Docker PM profile passes `VITE_POC_MODE=pm` as a build arg.

PM nav: **Program** · **Activity** · **Jira drafts** · **Integrations** (Rovo MCP) · **Credentials** · **Settings**

## Program hyperagent (interview → learn → act)

1. **Interview** — On first visit, Intake asks five questions (program, goals, tools, constraints, stakeholders). Answers build per-user program context.
2. **Fleet pulse** — After the interview, the hyperagent queues agent work automatically (no button press). Use **Fleet pulse** to re-run.
3. **Guidance** — Type guidance on the Program page or in a mission’s **Guidance Thread**; the hyperagent records it and may queue follow-up tasks.
4. **Manual override** — Agent cards still work after the interview completes.

## Accounts (login + signup)

1. **First boot** — complete the Hive setup wizard (admin + initial daily user).
2. **Login page** — use **Sign in** or **Sign up** to create more accounts (3–32 char username; password min 8). Signup is enabled after setup; new users get role `user` and a session cookie.
3. **PM task isolation** — fleet invokes use the logged-in Hive user id (no separate maistro signup required when using Hive UI only).
4. **Credentials** — **Credentials** nav → paste Jira/GitHub tokens; stored **Fernet-encrypted** under `~/.conductor/` (`credential_master.key` + `user_credentials.enc`). Secrets never returned by the API and are not kept in `sessionStorage`.

## Atlassian / MCP (container runtime)

Canonical MCP manifests: JFC [`container_registry/MCP_servers/`](../../../../container_registry/MCP_servers/README.md).

### Production (Force Convergence sandbox)

1. Save **Jira**, **Confluence**, and/or **Atlassian Rovo MCP** tokens under Hive **Credentials**.
2. Set container env when deploying: `ATLASSIAN_API_TOKEN`, `ATLASSIAN_SITE_URL` (e.g. `https://your-site.atlassian.net`).
3. **Integrations** lists seeded MCP servers; use **Test connection** (`POST /v1/mcp/test`) after credentials are saved.
4. Jira **creates** from the PM UI use **Jira drafts** (suggest → confirm) — not autonomous MCP posts.

### Local dev only (optional)

Engineers editing this template may use `.cursor/mcp.json` + OAuth in Cursor. That path does **not** run in leased sandboxes.

Reference: `config/atlassian-rovo-mcp.cursor.json`.

Docs: [Getting started with Atlassian Rovo MCP Server](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/).

## Multi-user API keys

`API_KEYS` accepts `user:secret` pairs (comma-separated):

```bash
API_KEYS=alice:changeme-alice,bob:changeme-bob
```

Clients send `Authorization: Bearer changeme-alice` — tasks are scoped to `alice`.

## Docker (PM profile)

```bash
docker compose -f docker-compose.yml -f docker-compose.pm-poc.yml --profile pm-poc up --build
```

The PM overlay sets `MAISTRO_POC_MODE=pm` and sample user keys. Sandbox docker.sock is still on the base compose service; omit or override for locked-down demos.

## Environment reference

| Variable | Service | Purpose |
|----------|---------|---------|
| `MAISTRO_POC_MODE=pm` | maistro, hive | Enable five PM agents + intent routing |
| `HIVE_POC_MODE=pm` | hive backend | Same gate for in-process engine |
| `VITE_POC_MODE=pm` | hive frontend build | Fleet UI + trimmed nav |
| `HIVE_LOG_LEVEL=debug` | hive backend | Verbose request + task logs in terminal |
| `VITE_DEBUG_API=false` | hive frontend | Disable `[hive]` lines in browser console |
| `API_KEYS=user:secret,...` | maistro | Per-user bearer mapping |
| `ATLASSIAN_ROVO_MCP_URL` | hive | Rovo MCP endpoint (default authv2 URL) |
| `ATLASSIAN_API_TOKEN` | cursor / hive | Optional if org enables MCP API token auth |

## Agents

Seeds live under `agents/{intake,program_manager,delivery,risk_dependency,reporting}/` with `agent.yaml` and `SOUL.md`.

Invoke via Hive: `POST /v1/agents/{id}/invoke` with `{ "capability": "...", "payload": {} }`.

Or maistro API: `POST /v1/maistro/agents/{id}/invoke` (requires `MAISTRO_POC_MODE=pm`).
