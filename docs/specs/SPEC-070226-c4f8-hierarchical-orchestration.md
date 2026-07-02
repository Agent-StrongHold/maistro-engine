---
id: SPEC-070226-c4f8
title: "Hierarchical orchestration: agent/skill portability across harnesses"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-07-02
substrate:
  - maistro-engine#ADR-058
  - maistro-engine#ADR-061526-f383
  - maistro-engine#ADR-101
  - maistro-engine#SPEC-208
implements:
  - maistro-engine#ADR-101
related:
  - maistro-engine#ADR-062
  - maistro-engine#ADR-070
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
tests: []
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-070226-c4f8: Hierarchical orchestration — agent/skill portability across harnesses

## Context

ADR-101 specifies portability: an agent built for one harness (e.g., Claude Code Conductor) can be
exported and run on another harness (e.g., Pi, OpenClaw). Hierarchical orchestration means a parent
harness can spawn sub-agents on foreign harnesses and collect results.

SPEC-208 (foreign harness adapter) exports agents. This SPEC completes the hierarchical part:
parent orchestrator discovers available foreign harnesses, selects one, spawns agents, and
aggregates results.

## Goals

- Agent export from one harness in a portable format (MCP manifest).
- Foreign harness discovery and capability advertisement.
- Hierarchical delegation: parent harness spawns agents on sub-harnesses.
- Result aggregation and error handling.

## Non-goals

- Cross-tenant orchestration (Stronghold).
- Peer-to-peer harness mesh (Phase 2).

## Decision

### Harness registry and discovery

```python
@dataclass
class HarnessAdvertisement:
    harness_id: str  # "pi-0", "openclaw-1"
    endpoint: str  # "https://pi.local:8000"
    capabilities: list[str]  # ["agent:run", "skill:import"]
    agent_roster: list[str]  # agent names available on this harness
    cost_multiplier: float = 1.0  # relative cost vs. local
    latency_multiplier: float = 1.0

class HarnessRegistry(Protocol):
    async def list_harnesses(self) -> list[HarnessAdvertisement]:
        """Discover all connected foreign harnesses."""
    
    async def get_harness(self, harness_id: str) -> HarnessAdvertisement:
        ...
```

### Hierarchical delegation

```python
class HierarchicalOrchestrator:
    """Parent harness orchestration."""
    
    async def spawn_on_harness(
        self,
        agent_name: str,
        harness_id: str,
        task: Task
    ) -> TaskResult:
        """
        Export agent, send to foreign harness, run, collect result.
        """
        # Get foreign harness
        harness = await self.registry.get_harness(harness_id)
        
        # Export agent (MCP manifest or equivalent)
        agent_def = await self.export_agent(agent_name)
        
        # POST to foreign harness
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{harness.endpoint}/v1/harness/sessions",
                json={
                    "agent": agent_def,
                    "task": task.to_dict()
                },
                headers={"Authorization": f"Bearer {self.harness_token}"}
            )
        
        return TaskResult.from_dict(response.json())
    
    async def spawn_wave_across_harnesses(
        self,
        agents: list[str],
        harnesses: list[str],
        task: Task
    ) -> TaskResult:
        """
        Parallel wave: spawn N agents on N harnesses, return best result.
        """
        results = await asyncio.gather(
            *[
                self.spawn_on_harness(agent, harness, task)
                for agent, harness in zip(agents, harnesses)
            ],
            return_exceptions=True
        )
        
        # Compare and return best
        valid_results = [r for r in results if not isinstance(r, Exception)]
        if not valid_results:
            raise AllHarnessesFailedError(results)
        
        return max(valid_results, key=lambda r: r.quality_score)
```

### Agent portability via MCP manifest

The export format (from SPEC-208) is an MCP server manifest + agent config YAML:

```yaml
# agent-export.yaml
name: "research-agent"
version: "1.0.0"
description: "Research and summarization"
mcp_manifest: {...}  # MCP server spec
agent_config:
  prompt: "..."
  memory_type: "episodic"
  tools: [...]
```

Foreign harness imports and runs this like any native agent.

### Error handling and fallback

```python
async def spawn_with_fallback(
    self,
    agent_name: str,
    harnesses: list[str],  # ordered by preference
    task: Task
) -> TaskResult:
    """Try harnesses in order until one succeeds."""
    for harness_id in harnesses:
        try:
            return await self.spawn_on_harness(agent_name, harness_id, task)
        except HarnessUnavailableError:
            continue  # try next
    
    raise NoAvailableHarnessError(harnesses)
```

## Acceptance criteria

- [ ] Harness registry returns all connected foreign harnesses.
- [ ] Agent export produces a valid MCP manifest + agent config.
- [ ] Hierarchical spawn succeeds: parent sends agent to foreign harness, foreign harness runs it,
      parent receives result.
- [ ] Wave across harnesses: multiple agents on multiple harnesses, best result returned.
- [ ] Fallback: if harness A unavailable, try harness B (property: at least one succeeds if any
      harness is up).
- [ ] Error from foreign harness is propagated (not silent failure).

## Testing

- Integration: parent harness spawns a real agent on a mock foreign harness.
- Fallback: harness A fails, harness B succeeds, overall call succeeds.
- Property: "hierarchical spawn always succeeds if at least one harness is available" (Hypothesis
  over harness availability).

## References

- [ADR-101: Foreign harness adapters](../adr/ADR-101-foreign-harness-adapters.md)
- [SPEC-208: Foreign harness adapter](SPEC-208-foreign-harness-adapter.md)
