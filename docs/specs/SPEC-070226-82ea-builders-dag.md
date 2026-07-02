---
id: SPEC-070226-82ea
title: "Builders pipeline as DAG with gated verify-and-revise loops"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-07-02
substrate:
  - maistro-engine#ADR-062
  - maistro-engine#ADR-066
  - maistro-engine#ADR-099
  - maistro-engine#SPEC-184
  - maistro-engine#SPEC-201
implements:
  - maistro-engine#ADR-099
related:
  - maistro-engine#ADR-068
  - maistro-engine#ADR-070
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
  - boundary
tests: []
layer: Agents
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-070226-82ea: Builders pipeline as DAG with gated verify-and-revise loops

## Context

Builders (spec → tests → code → review → retry) currently run as a flat ReAct loop. ADR-099
specifies a DAG-based orchestration where nodes are design stages (spec, test, code, review,
revise) and edges are control flow (spec complete → write tests; test pass → implement; review
pass → merge; review fail → revise). Gating rules decide when to loop back (insufficient coverage
→ revise tests; merge-conflict → retry).

## Goals

- Builders pipeline as a DAG (SPEC-201 already exists; this wires it).
- Gating rules (e.g., "if code coverage < 80%, loop back to test generation").
- Verify-and-revise loops (automated, bounded).
- Integration with graph executor (ADR-062) for orchestration.

## Non-goals

- Learning which gates work best (ADR-099 follow-up; gates are operator-tuned for Phase 1).
- AI-driven test generation (defer to Phase 2).

## Decision

### Builders DAG structure

```python
@dataclass
class BuildersDAG:
    """Pipeline DAG: stages are graph nodes."""
    stages = {
        "design": DesignStage(...),
        "test": TestStage(...),
        "implement": ImplementStage(...),
        "review": ReviewStage(...),
        "revise": ReviseStage(...),
    }
    
    edges = [
        ("design", "test"),      # spec complete
        ("test", "implement"),   # test complete
        ("implement", "review"), # code complete
        ("review", "revise"),    # review needs changes (gated)
        ("revise", "test"),      # loop back to test
    ]
    
    gates = [
        Gate("test.coverage", predicate=lambda result: result.coverage >= 80),
        Gate("review.approved", predicate=lambda result: result.approved),
    ]

# Equivalent to a GraphSpec that the executor runs
def builders_dag_to_graph(dag: BuildersDAG) -> GraphSpec:
    nodes = [NodeSpec(id=stage, strategy=stage) for stage in dag.stages.values()]
    # edges + gates become node connections
    return GraphSpec(nodes=nodes, ...)
```

### Verify-and-revise gates

```python
@dataclass
class Gate:
    name: str
    predicate: Callable[[StageResult], bool]  # returns True if stage passed gate
    max_iterations: int = 3

async def apply_gate(gate: Gate, stage_result: StageResult) -> bool:
    """Return True if gate passed (continue to next stage); False to loop back."""
    if stage_result.iterations >= gate.max_iterations:
        return True  # force forward even if gate fails
    
    return gate.predicate(stage_result)
```

### Revise stage (specialized)

```python
class ReviseStage(Stage):
    """
    Analyze review feedback and generate revisions.
    Input: code + review comments
    Output: revised code + change summary
    """
    
    async def execute(self, context: BuildersContext) -> ReviseResult:
        code = context.latest_code
        feedback = context.review_feedback
        
        # LLM: "Here's code. Here's feedback. Generate a revised version."
        revised = await self.llm.generate(
            prompt=f"Code:\n{code}\n\nFeedback:\n{feedback}\n\nRevised code:",
            max_tokens=4096
        )
        
        return ReviseResult(
            revised_code=revised,
            change_summary="Fixed: ..., Added: ...",
            iterations=context.iterations + 1
        )
```

### Loop termination

```python
# Loop terminates when:
# - All gates pass (code → review → approve).
# - Max iterations reached (safety valve, don't loop forever).
# - User cancels (manual stop).

async def run_builders_dag(dag: BuildersDAG, request: BuilderRequest) -> CodeResult:
    graph = builders_dag_to_graph(dag)
    executor = GraphExecutor(GraphRun(graph))
    
    result = await executor.run()
    
    if result.status == "success":
        return CodeResult(code=result.output)
    else:
        raise BuildersFailedError(result.reason)
```

## Acceptance criteria

- [ ] Builders DAG runs as a GraphRun (types match ADR-062).
- [ ] Gates are evaluated after each stage; on failure, control loops back to correct stage.
- [ ] Max iteration limit prevents infinite loops (property: iterations never exceed limit).
- [ ] Coverage gate (e.g., 80%) works: if coverage < 80% after test stage, loop back; if >= 80%,
      continue to implement.
- [ ] Review gate: if review is "approved", move to next; if "needs changes", loop to revise.
- [ ] Revise stage generates valid code (passes syntax check).

## Testing

- Integration: run a full Builders pipeline (design → test → implement → review → approve).
- Gate failure: design generates test that doesn't compile, gate rejects, revise fixes it.
- Loop limit: set max_iterations=2, verify loop terminates even if gate still fails.
- Property: "DAG runs to completion or hits iteration limit" (no hangs).

## References

- [ADR-099: Builders pipeline as DAG](../adr/ADR-099-builders-dag.md)
- [ADR-062: Graph Execution Protocol](../adr/ADR-062-graph-execution-protocol.md)
- [SPEC-201: Builders interactive session](SPEC-201-builders-interactive-session.md)
