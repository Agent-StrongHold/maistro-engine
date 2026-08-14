# Stream 4 Checkpoint 12: MCP, Skills, and Tool Exposure

Date: 2026-08-14
Source audited: `develop`

This checkpoint separates live catalog/control-plane behavior from actual execution exposure. The distinction is important for Stream 6 because MCP servers, Skills, ToolExposure, Binding, and authorization are related but not interchangeable.

## 1. Hive MCP server management is a live control-plane surface

Mounted `routes/mcp.py` supports:

- list MCP servers
- get server
- add/delete server
- health/connectivity checks
- test one/all configured servers
- list stored MCP tools
- scan endpoint stub
- discover endpoint stub

Mutating MCP routes are protected by Hive auth permission mappings.

Classification: `live MCP configuration/connectivity surface`.

## 2. MCP discovery endpoint is not actually wired

`POST /v1/mcp/discover` currently returns:

- `tools: []`
- `status: "scanning"`

and does not perform discovery.

Therefore the mounted API proves MCP configuration exists, but not that server tool discovery/exposure is fully wired.

Classification: `reachable endpoint with placeholder behavior`.

## 3. MCP tool listing is store-backed, not evidence of executable Binding

`GET /v1/mcp/tools` simply returns `stores.mcp_tools.values()`.

A tool appearing in this store does not by itself establish:

- Project visibility
- Binding
- credential scope
- Node exposure
- Invocation path
- actual provider health at execution time

### Stream 6 constraint

Treat stored MCPTool records as catalog/exposure inputs, not canonical Binding or authorization grants.

## 4. MCP connectivity has provider-specific credential resolution embedded in the client

`services.mcp_client.resolve_atlassian_token(user_id)` resolves in this order:

1. vault-backed/operator secret
2. environment secret
3. user encrypted credential store (`jira` or `atlassian_rovo_mcp`)

This is working compatibility behavior, but it means a deployment-wide token can win before the caller's user credential.

### Stream 3/6 migration direction

Canonical Binding/Credential resolution must make this precedence explicit rather than inheriting it accidentally.

Potential valid modes include:

- operator/deployment credential binding
- Project credential binding
- user-owned credential binding

The invocation should know which credential/resource was selected and why.

## 5. Current MCP test path is connectivity, not MCP execution

For Atlassian Rovo, the current headless test primarily verifies Jira REST/token availability. It can report a token as present even when the Jira site is not configured or full MCP transport is not verified.

For local HTTP MCP, the test is a basic HTTP reachability probe.

This is useful health/config UX, but should not be mistaken for end-to-end MCP Capability invocation.

## 6. Hive Skills are live content/catalog records

Mounted `routes/skills.py` provides:

- list/get/create/update/delete
- forge
- enable/disable toggle
- content scan

Skill content includes name, description, and parameters/tool-call schema.

Classification: `live Skill catalog/product surface`.

## 7. Skill CRUD deliberately does not provide full provenance/import security

The route performs the parser-level `security_scan` and fails closed on critical findings.

Its own documentation explicitly states this is **not** the full ADR-083 import gate. CRUD-created Skills do not automatically receive:

- salvage pass
- Warden scan
- T3 sandboxing
- `rescan_on_use` policy attachment/content-hash binding
- signing/provenance attestation

This truth-status distinction must survive migration.

### Stream 6/7 handoff

A Skill being `enabled=True` means catalog availability, not that it is safe/authorized/exposed for every Invocation.

## 8. Skill enabled state is not Project authorization

The live Skill model has a global `enabled` toggle. Current auth protects mutation of the catalog, but the Skill record itself is not a Project grant/deny.

Canonical flow should keep separate:

- Skill installed/enabled
- Skill security/provenance status
- Persona/Node/Graph desire to use it
- ToolExposure generated from it
- Project authorization/resource visibility
- Binding/Provider/Credential selection
- Invocation-time policy

## 9. MCP server existence is likewise not Project authorization

A server may be globally configured and healthy while a specific Project is not allowed to bind/use it.

The existing `maistro.projects.enabled_mcp_servers` and Persona/workspace tool defaults found in earlier checkpoints are configuration intent, not the authorization algorithm.

## 10. Current product surfaces should become canonical consumers, not be deleted blindly

Preserve:

- MCP setup/health UX
- server catalog
- provider-specific diagnostics
- Skill authoring/catalog UX
- content scanning
- enable/disable control

Replace/complete:

- placeholder MCP discovery
- ambiguous credential precedence
- raw store listing as execution exposure
- global enabled/config values as implicit permission

## Immediate handoffs

### Stream 3

MCP/Skill global catalog state should be constrained by canonical Project resource visibility and grants/denies; Persona remains outside authorization.

### Stream 6

Use MCPServer/MCPTool/Skill as inputs to Capability/ToolExposure/Binding. Make credential selection explicit and invocation-correlated. Do not infer executable exposure from catalog presence.

### Stream 7

Keep the existing setup/CRUD/diagnostic UX while switching backing services to canonical catalog/binding APIs.

## Reachability truth rule reinforced

A mounted endpoint can be real while its advertised operation remains a placeholder. `/v1/mcp/discover` is a concrete example: structural reachability is not end-to-end behavioral reachability.
