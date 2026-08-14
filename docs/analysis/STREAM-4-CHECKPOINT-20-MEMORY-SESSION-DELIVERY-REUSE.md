# Stream 4 Checkpoint 20: Memory, Session Search, Delivery, Code Registry, Repertoire

Date: 2026-08-14
Source audited: `develop`

This checkpoint classifies another group of currently unreachable service-layer capabilities. The goal is to preserve useful behavior without reviving their legacy ownership/lifecycle assumptions.

## Episodic retrieval

`maistro.memory.episodic.retrieval.ScoredEpisodicRetrieval` provides useful memory behavior:

- scope filtering
- lexical overlap ranking
- optional embedding cosine reranking
- confidence/weight scaling
- graceful lexical fallback when embedding lookup fails

This should be salvaged as a canonical memory retrieval service.

### Scope migration required

The current scope model is legacy:

- GLOBAL
- ORGANIZATION / `org_id`
- TEAM / `team_id`
- USER / `user_id`
- AGENT / `agent_id`

`matches_scope()` includes useful anti-leakage behavior, especially TEAM requiring matching org and constrained GLOBAL visibility, but the identifiers do not match the canonical convergence model.

Target scope vocabulary should be derived from the accepted ownership architecture, likely distinguishing at least:

- Workspace knowledge
- Project-scoped knowledge where needed
- User-private knowledge
- Node/Agent-specific knowledge
- Run-local working context handled separately from durable shared memory

Do not mechanically rename `org_id -> workspace_id` or `team_id -> project_id`; preserve semantics only where the ownership model actually matches.

## Memory consolidation

`maistro.memory.episodic.consolidation` is domain/service logic, not an execution framework.

Useful behavior to preserve:

- similarity-based merge proposals
- contradiction detection
- confidence reduction + review flags
- soft-delete/amendment behavior
- incremental application hooks
- batch observability counts

The existing `run_batch()` name does not make this a canonical Run. It is an ordinary service operation that can later execute inside a scheduled/manual Run when orchestration needs history, events, cancellation, or retry.

## Session search

`maistro.sessions.search` is a clean pure-query utility:

- stable cursor pagination
- date filtering
- substring query
- deterministic snippets/highlighting

This maps directly onto canonical Session persistence/query once Session ownership is normalized. It should not invent a Run, Node, or Invocation abstraction.

## Delivery

`maistro.delivery.dispatch` contains useful transport behavior but owns mechanics that need decomposition:

Preserve:

- channel abstraction/registry
- delivery target and payload domain
- idempotent duplicate suppression intent
- provider message IDs
- circuit-breaker integration
- delivery result status

Converge/remove from delivery ownership:

- retry loop as a competing physical-execution lifecycle
- idempotency key based on legacy `payload.metadata["task_id"]`
- delivery-specific attempt ownership where canonical Invocation/Attempt should provide execution identity/correlation

Target shape should treat delivery as a Capability/Binding/Invocation or product service invoked by a Node, with canonical Event/Artifact/Run correlation. Domain delivery policy may still choose whether a failed Invocation should be retried, but physical retries must not become a second universal Attempt model.

## Code registry

`maistro.code_registry.CodeRegistry` is a specialized signed-code registry and should remain conceptually distinct from:

- ADR/spec Registry
- CapabilityRegistry
- Template registry
- model/provider catalogs

Useful behavior:

- versioned refs
- strict semver parsing
- signature verification before registration
- exact resolution
- major-version compatibility checks

The package is currently structurally unreachable. If retained, wire it where signed executable code/templates are actually selected or validated, especially recovery/version-compatibility and tool/code execution paths. Do not create one generic "Registry" abstraction merely to eliminate nouns.

## Repertoire

`maistro.repertoire.repertoire_run()` implements a reuse-first problem-solving cascade:

`recall -> perform gate -> nearest priors -> improvise -> rehearse -> compose`

This is strategy/domain behavior, not a universal execution lifecycle despite the function name.

Preserve:

- reuse-first semantics
- stakes-aware perform gate
- nearest-prior lookup
- rehearsal verification
- composition of successful candidates

Target integration:

- as a reusable strategy/capability available to Nodes/Agents/RSI where appropriate
- execute expensive improvise/rehearse operations through canonical Run/Invocation infrastructure if they cross execution boundaries
- store resulting reusable patterns in the canonical memory/template/repertoire service chosen by the final service architecture

## Stream handoffs

### Stream 3

Memory scope migration must follow canonical Workspace/Project authorization and must not preserve old org/team identifiers as accidental permission semantics.

### Stream 6

Delivery invocation, provider/channel fulfillment, retries, and signed-code/tool resolution need to align with Binding/Invocation and canonical Attempt ownership.

### Stream 7 / services convergence

Session search, memory retrieval/consolidation, code registry, and repertoire are reusable services to wire into product paths after the spine is stable. Their current unreachability should not be solved by inventing new lifecycle authorities.

## Deletion posture

None of these service implementations is a delete-now candidate solely because the ratchet lists them as unreachable. Each contains reusable domain behavior. The correct next action is either:

1. wire the useful behavior through canonical product/runtime services, or
2. explicitly decide the capability is unwanted and remove its docs/tests/code together.
