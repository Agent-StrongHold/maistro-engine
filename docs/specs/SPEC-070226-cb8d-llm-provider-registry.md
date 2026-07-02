---
id: SPEC-070226-cb8d
title: "LLM provider / model registry, routing, and embeddings"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-07-02
substrate:
  - maistro-engine#ADR-079
  - maistro-engine#ADR-085
  - maistro-engine#SPEC-014
implements:
  - maistro-engine#ADR-079
related:
  - maistro-engine#ADR-094
  - maistro-engine#SPEC-270
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Tools
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-070226-cb8d: LLM provider / model registry, routing, and embeddings

## Context

Agents currently call the OpenAI-compatible gateway directly. ADR-079 specifies a unified provider
registry where operators declare available models (claude-3-opus, gpt-4-turbo, local-llama, etc.),
each with cost/latency/tier metadata, and a router that selects the best model for each call
based on task requirements (reasoning depth, latency budget, cost constraint).

## Goals

- Single source of truth for available LLM providers and models (registry).
- Per-model cost/latency/capability metadata (used by router + quota tracking per ADR-085).
- Router selects model based on task type, cost budget, reasoning requirements.
- Embedding models (vector generation) registry and routing.
- Fallback chain (if primary model unavailable, try secondary).

## Non-goals

- Fine-tuning model selection (ADR-079 follow-up).
- Multi-cloud vendor negotiation (Stronghold).

## Decision

### Provider registry structure

```python
@dataclass
class ModelMetadata:
    name: str  # "claude-3-opus", "gpt-4-turbo"
    provider: str  # "anthropic", "openai", "local"
    tier: Literal["fast", "balanced", "powerful"] = "balanced"
    cost_per_1k_input: float  # cents
    cost_per_1k_output: float
    latency_p50_ms: int
    reasoning_capable: bool = False
    max_tokens: int = 4096
    fallback_to: list[str] = field(default_factory=list)  # ["gpt-4-turbo", ...]

@dataclass
class EmbeddingModelMetadata:
    name: str  # "text-embedding-ada-002"
    provider: str
    dimension: int
    cost_per_1k_tokens: float

class LLMProviderRegistry(Protocol):
    async def list_models(self, filter_by: dict = None) -> list[ModelMetadata]:
        """List available models, optionally filtered by provider/tier."""
    
    async def get_model(self, name: str) -> ModelMetadata:
        """Fetch a specific model's metadata."""
    
    async def get_embedding_model(self, name: str) -> EmbeddingModelMetadata:
        ...

class LLMRouter(Protocol):
    async def select(self, task: Task, budget: dict = None) -> ModelMetadata:
        """
        Select the best model for the task.
        budget: {"max_cost_cents": 10, "max_latency_ms": 5000, "reasoning": true}
        """
    
    async def select_embedding(self, input_size_tokens: int) -> EmbeddingModelMetadata:
        ...
```

### Default config (INI-style or YAML)

```yaml
models:
  - name: claude-3-opus
    provider: anthropic
    tier: powerful
    cost_input: 0.15
    cost_output: 0.75
    latency_p50_ms: 800
    reasoning: true
    fallback: [gpt-4-turbo]
  
  - name: gpt-4-turbo
    provider: openai
    tier: powerful
    cost_input: 0.03
    cost_output: 0.06
    latency_p50_ms: 1200
    reasoning: false
    fallback: [gpt-3.5-turbo]

embeddings:
  - name: text-embedding-ada-002
    provider: openai
    dimension: 1536
    cost_per_1k: 0.0001
```

### Router logic

```python
class CostAwareRouter(LLMRouter):
    def __init__(self, registry: LLMProviderRegistry):
        self.registry = registry
    
    async def select(self, task: Task, budget: dict = None) -> ModelMetadata:
        budget = budget or {}
        max_cost = budget.get("max_cost_cents", float('inf'))
        max_latency = budget.get("max_latency_ms", float('inf'))
        reasoning_required = budget.get("reasoning", False)
        
        models = await self.registry.list_models()
        
        # Filter by constraints
        candidates = [
            m for m in models
            if m.cost_per_1k_input <= max_cost
            and m.latency_p50_ms <= max_latency
            and (not reasoning_required or m.reasoning_capable)
        ]
        
        if not candidates:
            raise NoEligibleModelError(budget)
        
        # Pick the fastest (or cheapest, or best-reasoning, depending on priority)
        return min(candidates, key=lambda m: m.latency_p50_ms)
```

### Integration with quota tracking (ADR-085)

```python
# When a task calls an LLM via the router:
model = await router.select(task, budget)
response = await llm_client.call(model=model.name, ...)

# Quota tracker logs this call with the model's cost metadata
quota_tracker.record_usage(
    provider=model.provider,
    model=model.name,
    input_tokens=response.input_tokens,
    output_tokens=response.output_tokens,
    cost_cents=(
        response.input_tokens / 1000 * model.cost_per_1k_input +
        response.output_tokens / 1000 * model.cost_per_1k_output
    )
)
```

## Acceptance criteria

- [ ] LLMProviderRegistry.list_models() returns all configured models (property: ordering
      is consistent; no duplicates).
- [ ] Router selects a model that satisfies the budget constraints (cost, latency, reasoning).
- [ ] Router falls back to next in chain if primary is unavailable (circuit breaker test).
- [ ] Embedding model selection works independently (separate registry + router).
- [ ] Cost tracking in quota system uses registry metadata (no hardcoded pricing).
- [ ] Unknown model name raises ModelNotFoundError (not silent fallback).

## Testing

- Unit: router selection with various budgets (cheap+fast vs. powerful vs. reasoning).
- Integration: a task specifies budget, router picks correct model, quota tracker logs correct cost.
- Fallback chain: mark primary unavailable, confirm router tries secondary.
- Property: router selection always respects all constraints (no over-budget).

## Open questions

- Should the registry be hot-reloadable (operators update config without restart)? (Defer to Phase 2.)
- Multi-cloud provider failover (detect one provider is down, switch to another)? (Defer to Phase 2.)

## References

- [ADR-079: LLM Provider Registry](../adr/ADR-079-llm-provider-routing.md)
- [ADR-085: Cost, Quota, Rate Limiting](../adr/ADR-085-cost-quota-rate-limiting.md)
