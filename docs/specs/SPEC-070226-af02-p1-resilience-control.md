---
id: SPEC-070226-af02
title: "P1 Resilience: depth/compaction/retry enforcement with control-scope steering"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-07-02
substrate:
  - maistro-engine#ADR-038
  - maistro-engine#ADR-062
  - maistro-engine#ADR-066
implements:
  - maistro-engine#ADR-066
related:
  - maistro-engine#ADR-071
  - maistro-engine#SPEC-248
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
tests: []
layer: Reliability
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-070226-af02: P1 Resilience — depth/compaction/retry enforcement with control-scope steering

## Context

ADR-066 specifies P1 (Phase 1) resilience: depth limits on task retries, compaction (merging similar
retry attempts into one cohesive signal), and a control-scope enforcement mechanism to steer
remediation choices (escalate vs. retry vs. fail-fast). ADR-038's reliability taxonomy provides
the classification (Shallow, P1, P2, P3); this SPEC realizes the P1 enforcement.

Primitives already exist (retry/backoff primitives in maistro.resilience); this SPEC wires them into
the graph executor, conduit, and observability pipeline.

## Goals

- Enforce retry depth limits per task (configurable: default 3 retries max).
- Compact similar retry attempts (same error type/code, within time window) into one `CompactedRetry`
  signal rather than spamming the log.
- Control-scope gating: on each retry decision, consult a `ResiliencePolicy` (per-agent, per-layer,
  per-error-type) to decide escalate (to parent/super-planner) vs. retry vs. fail-fast.
- Emit P1 resilience events (retry.attempted, retry.succeeded, retry.exhausted, retry.compacted)
  per ADR-037.

## Non-goals

- P2/P3 resilience (deeper learning loops, jailbreak recovery) — Phase 2+.
- Auto-tuning resilience policy (operator-set, not learned in P1).
- Circuit breaker (ADR-038 Shallow; separate from P1 control).

## Decision

### Depth enforcement in the graph executor

```python
# maistro/graph/executor.py

@dataclass
class RetryBudget:
    max_retries: int = 3
    compaction_window_ms: int = 5000  # merge retries within this window
    current_attempt: int = 0
    attempts: list[NodeRunAttempt] = field(default_factory=list)  # history

async def execute_node(node: NodeSpec, budget: RetryBudget) -> NodeRun:
    """Execute a node with retry budget enforcement."""
    while budget.current_attempt < budget.max_retries:
        try:
            result = await _execute_once(node)
            emit("node.success", node=node.id, attempt=budget.current_attempt)
            return result
        except Exception as e:
            budget.current_attempt += 1
            budget.attempts.append(NodeRunAttempt(error=e, timestamp=now()))
            
            if budget.current_attempt >= budget.max_retries:
                compacted = compact_attempts(budget.attempts, budget.compaction_window_ms)
                emit("node.retry_exhausted", node=node.id, compacted=compacted)
                raise
            
            # Check control scope policy
            policy = resolve_policy(node, e)  # per-agent, per-layer, per-error
            action = policy.decide(budget.current_attempt, e)  # escalate | retry | fail
            
            if action == "escalate":
                emit("node.escalated", node=node.id, reason=str(e))
                raise  # propagate to parent/orchestrator
            elif action == "fail":
                emit("node.retry_failed", node=node.id, reason=policy.reason)
                raise
            else:  # retry
                emit("node.retry_attempted", node=node.id, attempt=budget.current_attempt, error=str(e))
                await asyncio.sleep(backoff(budget.current_attempt))  # exponential backoff
```

### ResiliencePolicy and control-scope gating

```python
@dataclass
class ResiliencePolicy:
    """Per-agent, per-layer, per-error-type policy."""
    agent_id: str
    layer: Layer  # Foundation, Orchestration, Agents, etc.
    error_code: str  # e.g. "rate_limit", "timeout", "llm_refusal", "user_error"
    max_p1_retries: int = 3
    backoff_strategy: Literal["exponential", "linear"] = "exponential"
    escalate_on: set[str] = field(default_factory=set)  # error codes that trigger escalation
    
    def decide(self, attempt: int, error: Exception) -> Literal["retry", "escalate", "fail"]:
        code = classify_error(error)
        if code in self.escalate_on:
            return "escalate"
        if attempt >= self.max_p1_retries:
            return "fail"
        return "retry"

class ResiliencePolicyStore(Protocol):
    """Agent/layer/error → ResiliencePolicy lookup."""
    async def get(self, agent_id: str, layer: Layer, error_code: str) -> ResiliencePolicy:
        ...

# Default policy: escalate on LLM refusals, user errors; retry on transient (rate limit, timeout)
DEFAULT_POLICIES = {
    ("*", "Agents", "llm_refusal"): ResiliencePolicy(
        agent_id="*", layer=Layer.Agents, error_code="llm_refusal",
        escalate_on={"llm_refusal"}
    ),
    ("*", "Tools", "rate_limit"): ResiliencePolicy(
        agent_id="*", layer=Layer.Tools, error_code="rate_limit",
        escalate_on=set(), max_p1_retries=5, backoff_strategy="exponential"
    ),
}
```

### Compaction: merge similar retry attempts

```python
@dataclass
class CompactedRetry:
    error_code: str
    count: int
    first_timestamp: float
    last_timestamp: float
    common_cause: str  # inferred or user-provided summary

def compact_attempts(
    attempts: list[NodeRunAttempt],
    window_ms: int
) -> CompactedRetry:
    """Group retry attempts by error code within time window."""
    if not attempts:
        return None
    
    # All attempts within window_ms of the first attempt are grouped
    first_time = attempts[0].timestamp
    grouped = [a for a in attempts if (a.timestamp - first_time) < window_ms / 1000]
    
    codes = [a.error_code for a in grouped]
    code = codes[0]  # assume all same or pick most common
    
    return CompactedRetry(
        error_code=code,
        count=len(grouped),
        first_timestamp=first_time,
        last_timestamp=grouped[-1].timestamp,
        common_cause=infer_cause(grouped)  # LLM or heuristic summary
    )
```

### Observability (ADR-037)

```python
# Events emitted:
emit("node.retry_attempted", {
    "node_id": "...",
    "attempt": 2,
    "error_code": "rate_limit",
    "backoff_seconds": 4
})

emit("node.retry_exhausted", {
    "node_id": "...",
    "total_attempts": 3,
    "compacted": CompactedRetry(...)
})

emit("node.escalated", {
    "node_id": "...",
    "reason": "llm_refusal",
    "escalate_to": "orchestrator"  # or parent node
})
```

Events are tagged with `source: "resilience.p1"` for filtering.

### Integration points

- **Graph executor** (`maistro/graph/executor.py`): wrap `execute_node` with `RetryBudget` logic.
- **Conduit** (`maistro/conduit.py`): pass resilience policy context down to route handlers.
- **Container** (`maistro/container.py`): wire `ResiliencePolicyStore` (protocol + in-memory default).
- **Observability** (`maistro/observability/`): emit retry events per ADR-037.

## Acceptance criteria

- [ ] A `NodeRun` with `max_retries=3` fails after exactly 3 failed attempts (property: no
      off-by-one on retry count).
- [ ] Two retries of the same error code within the compaction window (5s default) are merged into
      one `CompactedRetry` with `count=2`; retries after the window are separate.
- [ ] `ResiliencePolicyStore.get(agent, layer, error_code)` returns a policy; unknown combinations
      fall back to a default policy (exponential backoff, no escalation).
- [ ] On a rate-limit error with a retry policy that allows retries, the node pauses with
      exponential backoff (2s, 4s, 8s) and retries automatically.
- [ ] On an LLM refusal error with an escalate policy, the node emits `node.escalated` and
      propagates the exception to the parent/orchestrator (not retried locally).
- [ ] Every retry attempt emits a `node.retry_attempted` event; exhaustion emits
      `node.retry_exhausted` (property: exactly 4 events total for 3 retries + 1 exhaustion).
- [ ] A compacted retry has `count >= 2`; single attempts are never compacted.
- [ ] Control-scope policy is consulted for every retry decision (not just first/last attempt).

## Testing

- Unit: `RetryBudget` enforcement (no retries after max), `compact_attempts` (same code within
  window, different codes separate).
- Unit: `ResiliencePolicy.decide()` per error code (escalate, retry, fail branches).
- Integration: a graph node that throws rate-limit errors up to 5 times, retries automatically
  per policy, and succeeds on the 4th attempt.
- Integration: a graph node that throws llm_refusal, policy escalates, parent catches the
  escalation and routes to a different sub-agent.
- Property (formal/): "retry count never exceeds max_retries regardless of error type" (use
  Hypothesis to generate error sequences).
- Load test: 100 concurrent nodes with mixed retry policies; verify no thread-safety issues.

## Open questions

- Should P1 retry decisions be logged (machine-readable audit) or just emitted as events? (Leaning:
  events only, audit trail is in the event log per ADR-037.)
- Default compaction window (5s) — tunable per-agent or global? (Global for Phase 1, per-agent
  policy in Phase 2.)
- Should escalation to a parent/orchestrator automatically trigger re-routing to a different
  sub-agent, or does the parent decide that? (Parent decides; escalation just signals the issue.)

## References

- [ADR-066: P1 Resilience and Control](../adr/ADR-066-p1-resilience-control.md)
- [ADR-038: Reliability Taxonomy](../adr/ADR-038-reliability-taxonomy.md)
- [ADR-062: Graph Execution Protocol](../adr/ADR-062-graph-execution-protocol.md)
- [ADR-037: Observability](../adr/ADR-037-observability.md)
