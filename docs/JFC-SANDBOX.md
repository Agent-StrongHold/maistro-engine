# maistro-engine — maistro sandbox template

## Purpose

Run **Hive Conductor** (UI + API on **8101**) and **maistro-core** (agents, tasks, MCP clients) inside a **container platform** user sandbox — independent of the Vibe Hosting Launch shell.

## Image

| Field | Value |
|-------|--------|
| Dockerfile | [`packages/hive-conductor/Dockerfile`](../packages/hive-conductor/Dockerfile) |
| Build context | maistro-engine repo root (monorepo packages copied in Dockerfile) |
| Exposed port | 8101 |
| Health | `GET /health` → `pm_poc_mode` optional |

```bash
docker build -f packages/hive-conductor/Dockerfile -t maistro-engine .
docker run --rm -p 8101:8101 \
  -e ATLASSIAN_SITE_URL=https://your-org.atlassian.net \
  -e ATLASSIAN_API_TOKEN=*** \
  maistro-engine
```

## Broker integration (target)

1. Extend sandbox broker `type` enum with `maistro_engine` (see [`container_registry/user_containers/sandboxes/maistro-engine/README.md`](../../sandboxes/maistro-engine/README.md)).
2. Runner starts container from `maistro-engine` image.
3. Vibe Hosting catalog links to `web_ui.url` from lease response (same pattern as Claude Code `web_terminal.url`).

## Environment (container)

| Variable | Purpose |
|----------|---------|
| `HIVE_POC_MODE=pm` | Optional PM demo overlay only |
| `MAISTRO_POC_MODE=pm` | PM fleet in maistro-core |
| `ATLASSIAN_SITE_URL` | Jira/Confluence Cloud site |
| `ATLASSIAN_API_TOKEN` | Headless Atlassian auth |
| `ATLASSIAN_EMAIL` | Optional; defaults to token-as-user for REST |
| `ATLASSIAN_ROVO_MCP_URL` | Rovo endpoint (default authv2) |
| `FILESYSTEM_MCP_URL` | Loopback filesystem MCP sidecar |

## Multi-agent / multi-MCP

- **Agents:** engineering registry (default) or PM fleet when `HIVE_POC_MODE=pm`.
- **MCP:** seeded from [`container_registry/MCP_servers/`](../../../../MCP_servers/README.md); test via `POST /v1/mcp/test`.
- **Credentials:** Fernet vault under `~/.conductor/` in container.

## Related

- Deployment: [`../../../../docs/MAISTRO-ENGINE-SANDBOX.md`](../../../../docs/MAISTRO-ENGINE-SANDBOX.md)
- PM demo runbook: [`PM_POC_RUNBOOK.md`](PM_POC_RUNBOOK.md)
