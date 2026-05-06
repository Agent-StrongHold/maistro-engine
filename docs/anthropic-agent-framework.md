# Agent Architecture — Research & Design Reference

Sources:
- [How Anthropic Thinks About Agents, Workflows, and Tasks](https://shellypalmer.com/2026/04/how-anthropic-thinks-about-agents-workflows-and-tasks/) (Barry Zhang / Shelly Palmer, April 2026)
- Meta agent graph / hyperagent patterns

---

## Primary Pattern: Hyperagent Graph

Maistro's primary execution model is a **hyperagent graph**: a directed graph of
specialized sub-agent nodes orchestrated by a top-level hyperagent (the conductor).

```
                    ┌─────────────┐
                    │  CONDUCTOR  │  ← hyperagent: owns routing decisions
                    │ (hyperagent)│
                    └──────┬──────┘
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
     ┌─────────┐     ┌─────────┐     ┌──────────┐
     │ PLANNER │────▶│  CODER  │────▶│ REVIEWER │
     └─────────┘     └─────────┘     └──────────┘
                           ▲                │
                           │  retry edge    │ approved=False
                           └────────────────┘
```

**Key distinctions from Anthropic's single-agent loop:**

| Property | Single agent (AGENT mode) | Hyperagent graph (GRAPH mode) |
|---|---|---|
| Who decides what to do next | The model (one actor) | Hyperagent node (routing oracle) |
| Parallelism | Sequential | Nodes can run in parallel branches |
| Role specialization | One prompt, many responsibilities | Each node has a scoped prompt + tools |
| Failure isolation | One error can abort the loop | Failed node surfaced per-node; hyperagent can reroute |
| Topology | Implicit (model decides) | Explicit (`GraphConfig.edges`) |
| Audit trail | Single trajectory | Per-node `GraphNodeResult` trace |

The hyperagent is **not** a full agent in the loop sense — it does not execute
work. It receives the output of a completed node and emits the `next_node`
routing decision. This keeps the hyperagent's context small and its decisions
auditable.

---

## Execution Modes (`ExecutionMode`)

| Mode | Control flow owner | When to use |
|---|---|---|
| `TASK` | n/a — single call | Summarization, classification, extraction. Predictable cost. |
| `WORKFLOW` | Developer (fixed sequence) | Known steps that don't require mid-run adaptation. Default. |
| `AGENT` | Model (autonomous loop) | Single-role ambiguous problems with verifiable outputs (e.g. coding with tests). |
| `GRAPH` | Hyperagent node (dynamic routing) | Multi-role tasks: plan → code → review → retry cycles. Primary maistro pattern. |

`WORKFLOW` is the conservative default in `TaskCreate`. `GRAPH` requires a
`graph_config` in the request body.

---

## Graph Topology Models

### `GraphConfig`
```python
class GraphConfig(BaseModel):
    nodes: list[AgentRole]          # participating sub-agent nodes
    edges: list[GraphEdge]          # directed edges, optionally conditional
    entry: AgentRole                # first node to activate (default: PLANNER)
    hyperagent: AgentRole           # orchestrating node (default: CONDUCTOR)
    max_cycles: int                 # loop cap — prevents runaway graphs (1–20)
```

### `GraphEdge`
```python
class GraphEdge(BaseModel):
    from_role: AgentRole
    to_role: AgentRole
    condition: str | None           # e.g. "review.approved is False"
                                    # None = always traverse
```

### `GraphNodeResult`
Emitted per node during graph execution. Carries `role`, `success`, `output`,
`tokens_used`, and the hyperagent's `next_node` decision.

### `HyperagentOutput`
Extends `ConductorOutput` with `graph_config`, `node_results: list[GraphNodeResult]`,
and `total_cycles`. Returned by the conductor when `execution_mode=GRAPH`.

---

## Example: Standard Engineering Task Graph

```json
{
  "description": "Add rate limiting to the /tasks endpoint",
  "execution_mode": "graph",
  "graph_config": {
    "nodes": ["planner", "coder", "reviewer"],
    "edges": [
      {"from_role": "planner",   "to_role": "coder"},
      {"from_role": "coder",     "to_role": "reviewer"},
      {"from_role": "reviewer",  "to_role": "coder", "condition": "review.approved is False"},
      {"from_role": "reviewer",  "to_role": null}
    ],
    "entry": "planner",
    "hyperagent": "conductor",
    "max_cycles": 3
  }
}
```

The reviewer→coder back-edge fires only when `review.approved is False`, capped
at 3 full cycles. The hyperagent evaluates the condition against the reviewer's
`ReviewOutput` and emits the routing decision.

---

## Anthropic Framework Reference

Barry Zhang's four criteria remain valid for deciding *whether* to build a
graph at all (vs. a simpler workflow):

1. **Task ambiguity** — if every step is known, a `WORKFLOW` is cheaper and
   more reliable. Use `GRAPH` when intermediate outputs determine the next step.
2. **Token economics** — each additional node in the graph multiplies token
   spend. `max_cycles` is the primary cost control; set it conservatively.
3. **Capability reliability** — errors inside a node propagate to the hyperagent's
   routing decision. Weak sub-agents produce bad routing signals.
4. **Error cost** — high-stakes nodes (deploy, infra writes) should have a human
   approval edge, not an automatic back-edge.

---

## Observability

| Signal | Where | What it tells you |
|---|---|---|
| `conductor_start` log | conductor.py | execution_mode, tier, model |
| `conductor_trajectory` log | conductor.py | For GRAPH: full edge list, nodes, cycle count. For others: subtask count, review score. |
| `GraphNodeResult.tokens_used` | HyperagentOutput | Per-node token cost — use to find expensive nodes |
| `llm_tokens_used_total` histogram | metrics.py | p50/p95 total tokens per call; alert when p95 > `max_tokens_per_task` |

---

## Remaining Gaps

1. **Graph execution engine** — `conductor.py` currently runs a single-pass agent.
   Phase 2 (per the existing comment) should implement the actual node-dispatch
   loop: iterate nodes, call the appropriate sub-agent, pass output to the
   hyperagent for routing, repeat up to `max_cycles`.

2. **Parallel branch support** — `GraphConfig.edges` can model fan-out (one node
   → multiple nodes) but the executor doesn't yet run branches concurrently.
   Use `asyncio.gather` over outgoing edges with no conditions.

3. **`GraphNodeResult` population** — the current `HyperagentOutput` is built at
   the end of a single conductor run. Once Phase 2 dispatches per-node, each
   `AgentRole` call should append a `GraphNodeResult` to the list.

4. **Condition evaluation** — edge conditions are free-text strings today. A
   structured `ConditionExpr` (field, operator, value) would make evaluation
   deterministic and auditable without relying on the hyperagent to parse prose.
