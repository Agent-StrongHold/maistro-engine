# Stream 4 Checkpoint 11: Agent, Chat, and Tool Execution Bypasses

Date: 2026-08-14
Source audited: `develop`

This checkpoint traces the mounted Agent invoke and chat tool paths. These are important convergence consumers because they execute real tools and workflows outside canonical Run/Attempt/Binding/Invocation even though newer execution abstractions exist elsewhere.

## 1. Mounted Agent API explicitly separates workspace visibility from invocation

`routes/agents.py` documents that workspace-scoped agents are materialized and visible, but `POST /{agent_id}/invoke` was deliberately **not** made workspace-aware because per-Persona dispatch/tool wiring was not implemented.

That is a useful truth-status statement: existing workspace Agent objects are product/configuration state, not a complete execution binding.

## 2. Agent invoke is a direct compatibility execution path

In PM POC mode, `POST /v1/agents/{agent_id}/invoke`:

- rejects some gated Jira-writing capabilities
- derives user ID
- imports chat completion `_execute_tool`
- executes the named capability directly
- returns `{status: completed, capability, result}`
- writes an audit entry

It does not create or correlate:

- canonical Run
- NodeRun
- Attempt
- Binding
- Invocation
- canonical Event/Checkpoint

Classification: `live compatibility bypass -> migrate to canonical Invocation/Run`.

## 3. AuthMiddleware intentionally exempts `/invoke` from elevation checks

Hive `AuthMiddleware._required_permission()` returns no special elevated permission for paths ending in `/invoke`.

The route remains authenticated because it is under `/v1/`, but its high-risk authorization posture currently depends on:

- PM-POC mode
- capability-specific `is_gated()` checks
- behavior inside `_execute_tool`

It does not use canonical Project resource authorization.

### Stream 3/6 constraint

Do not preserve `/invoke` as a permanent bypass. Once canonical Agent/Node/Binding execution exists, route invocation should resolve the target resource + authorization and create a canonical Invocation/Run or reject.

## 4. `_execute_tool` is a global dispatch map, not capability execution infrastructure

`services.chat_completion._execute_tool(tool_name, args, user_id)`:

1. resolves Jira PAT for the user
2. looks up `tool_name` in `_TOOL_HANDLERS`
3. calls the handler directly

There is no canonical Binding/Provider/Invocation or project scope in this dispatch.

The handler map covers multiple domains, including:

- Jira/Confluence/Airtable
- web search / browse URL
- Agent CRUD
- metrics
- dashboard mutation
- memory/profile operations
- workflow list/create/run/eval mutation
- hill climb / workflow mutation

This is a large live capability surface embedded inside chat product code.

Classification: `live private ToolExposure/Invocation layer`.

## 5. Unknown tool names fail open to `poll_jira`

The current dispatcher uses:

`_TOOL_HANDLERS.get(tool_name, _tool_poll_jira)`

Therefore an unknown capability/tool name does not return “unknown tool” or deny. It executes the Jira polling handler instead.

This is surprising behavior and should not be preserved in canonical capability execution.

### Stream 6 acceptance requirement

Unknown/unbound capability names should fail closed with an explicit typed error. Provider fallback may select another provider for a **known Capability/Binding**, but must not silently reinterpret an unknown capability as an unrelated tool.

## 6. Chat Agent-management tools operate on the flat global Agent store

`create_agent_button`, `modify_agent_button`, `remove_agent_button`, and `list_agent_buttons` mutate/read `stores.agents` directly.

They do not use the workspace-aware ownership checks implemented in `routes/agents.py`.

This means the live chat tool path and the live Agent HTTP CRUD path have different ownership semantics.

### Stream 3 / Stream 7 handoff

Canonical migration should have one ownership/resource resolution path shared by UI/API/chat surfaces. Chat should not be able to mutate a broader flat Agent namespace than the HTTP resource API permits.

## 7. Hive `execute_dag` has more live production callers than the primary DAG route and chat

The private Hive graph executor is reached from multiple mounted/product paths:

- mounted `POST /v1/dags/{id}/run`
- chat `_tool_run_workflow()`
- the mounted optimizer endpoint through `routes/optimizer.py`
- optimizer validation through `validation_gate.py`
- the registered chat `hill_climb` tool through `services/substrate_tools.py`, which can call it repeatedly

`_tool_run_workflow()` itself:

- reads DAG from `stores.dags`
- creates a synthetic DagRun ID/store record
- calls `services.graph_runner.execute_dag(dag_data, user_id=user_id)`
- appends synthetic node events
- adapts the result into eval-judge shape
- returns `status=completed`

Classification: `live private execution authority with multiple production consumers`.

### Stream 5 acceptance requirement

Migration of `execute_dag` is not complete when only the normal DAG route and chat workflow tool are moved. The optimizer, validation-gate, and hill-climb consumers must move in the same convergence inventory or retain an explicit tested compatibility adapter until they do. Their optimizer/iteration semantics are specialized behavior to preserve; their private universal execution lifecycle is not.

## 8. Chat workflow event/result projection loses failure semantics

`_tool_run_workflow()` appends `pm_node_completed` for every node result without checking the node's `success` field.

Its temporary eval adapter similarly assigns:

- `phase = "completed"`
- `error_code = None`
- `error_message = None`

for each result.

The returned tool response also reports top-level `status="completed"`.

Therefore failed node execution can be projected as completed through this path.

### Streams 2/5 handoff

Canonical Event and Run/NodeRun state should remove this result-reconstruction layer. Product projections should consume authoritative canonical lifecycle state instead of synthesizing it from loosely shaped dictionaries.

## 9. Chat workflow creation bypasses the mounted DAG route's ownership/audit/edit-lock semantics

`_tool_create_workflow()` writes a raw DAG dict directly into `stores.dags`.

It does not go through `routes/dags.create_dag()` and therefore does not automatically share all route-level schema/default/audit behavior.

Similarly, `update_eval` mutates the stored DAG dict directly.

This is another instance of product surfaces having independent mutation paths over the same domain store.

### Stream 7 migration requirement

Chat, API, UI, and CLI should call a shared canonical Graph/GraphTemplate service/repository rather than separately mutating raw product stores.

## 10. User integration credential resolution occurs inside product handlers

Chat tool helpers resolve Jira/Airtable/Confluence credentials themselves using env fallbacks and UserCredentialStore.

This is useful working behavior but embeds credential-selection policy deep in product code.

### Stream 6 direction

Move credential selection/materialization to canonical Binding/Invocation while preserving supported environment/deployment fallback only where intentionally allowed.

## 11. Agent and chat product state remains valuable

Do not treat the entire routes/agents or chat completion subsystem as disposable merely because execution wiring is non-canonical.

Preserve product behavior such as:

- materialized agent roster
- workspace-visible agents
- chat tool UX
- PM-specific capabilities
- gated write confirmation UX
- audit records
- reusable workflow/agent creation where desired

Replace universal execution/resource mechanics:

- flat/global ownership bypasses
- direct tool dispatch
- direct credential lookup
- synthetic completed status
- private graph execution
- unknown-tool fallback

## Immediate handoffs

### Stream 2

Chat/workflow synthetic `pm_node_*` events should become projections from canonical Event/NodeRun state.

### Stream 3

Unify Agent/workflow resource ownership across HTTP and chat. `/invoke` cannot remain a permanent authorization bypass.

### Stream 5

Treat all verified `execute_dag` consumers as migration callers: the mounted DAG route, chat `_tool_run_workflow`, optimizer route/validation path, and chat `hill_climb`/substrate path. Do not declare the private Hive executor retired while any of these production consumers still depend on it.

### Stream 6

Treat `_TOOL_HANDLERS` + `_execute_tool` as a live private capability/invocation surface to migrate. Unknown tools must fail closed.

### Stream 7

Preserve the chat/agent/workflow UX, but route mutations and execution through shared canonical services rather than raw `stores.*` dictionaries.

## Priority

High. These paths are mounted/reachable and can bypass newer canonical-looking infrastructure. Leaving them until “cleanup” would preserve the old execution ontology as the actual product path even after core convergence lands.
