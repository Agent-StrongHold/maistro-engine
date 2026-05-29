---
id: ADR-058
title: "maistro-design — composable design skills + design systems package"
repo: maistro-engine
kind: adr
status: Proposed
created: 2026-05-29
substrate:
  - maistro-engine#ADR-019
  - maistro-engine#ADR-031
  - maistro-engine#ADR-032
  - maistro-engine#ADR-041
related:
  - maistro-engine#ADR-033
implements: []
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Foundation
owners:
  - '@BlakeMatthews-dev'
---

# ADR-058 — maistro-design: composable design skills + design systems package

## Context

`maistro-canvas` provides a pixel-level compositor (layers, PIL assembly, image-gen jobs). It has no concept of reusable design *workflows*, brand specifications, or the structured "ask before generating" discipline that reduces LLM redirect loops.

`open-design` (nexu-io/open-design) demonstrates two patterns worth adopting:

1. **Composable Skills** — atomic design-capability units (prototype / deck / template / design-system / image / video / audio) each with a discovery form that must be completed before generation.
2. **Design Systems** — portable brand specifications (colors, typography, spacing, tokens.css, DESIGN.md) that any skill can consume as style context.

The gap: nothing in maistro-engine bridges these two patterns with the engine's security model (Warden, trust tiers, RLPHD feedback loop) or its graph substrate (DAG nodes, A2A delegation).

## Decision

Create a new first-class package `maistro-design` with the following shape:

```
packages/maistro-design/
└── src/maistro_design/
    ├── types.py        # DesignSkill, DesignSystem, DesignProject, enums, errors
    ├── protocols.py    # runtime_checkable Protocol interfaces
    ├── trust.py        # TrustTier, TrustReviewRecord, TrustBanishList, TrustReviewQueue
    ├── skills/         # InMemoryDesignSkillRegistry + 9 built-in skills
    ├── systems/        # InMemoryDesignSystemRegistry + DesignSystemLoader
    ├── engine.py       # DesignEngine — discovery → Warden → prompt-stack → canvas/A2A
    └── nodes.py        # DesignOrchestrateNode registered under kind "design.orchestrate"
```

### Key decisions

1. **Separate package, not a canvas extension.** Canvas = pixel compositor. Design = skill/system/workflow orchestration. The boundary prevents canvas from accumulating unrelated concerns.

2. **Engine builds prompt stack; does not call an LLM.** Consistent with ADR-019's library-first, protocol-driven DI philosophy. Caller passes the assembled prompt to maistro-core's conduit.

3. **Trust contamination is per-session and monotonically decreasing.** Each `DesignEngine` instance starts at `TrustTier.T0`. Loading a lower-trust component permanently reduces `context_trust_tier` for that instance. Session isolation is the caller's responsibility.

4. **All user input flows through Warden before trust assignment.** Discovery responses default to `TrustTier.T3`. Warden scans each response; skull-flagged content raises `TrustBannedError`. Every scanned input enqueues a `TrustReviewRecord` for async admin review.

5. **Admin trust decisions feed an RLPHD loop.** Admin choices (keep / upgrade / improve+upgrade / banish) update `TrustBanishList` and provide the preference signal that improves Warden's future recommendations (Reinforcement Learning for Policy via Human Decisions — "Ralph'd").

6. **Engine registers as a DAG node.** `DesignOrchestrateNode` (kind `"design.orchestrate"`) wraps `DesignEngine.generate()` so design workflows compose with the existing maistro-core graph executor.

## Acceptance criteria

```gherkin
# Trust tier
Scenario: TrustTier.min() is commutative and monotone
  Given TrustTier.T0
  When min(T2) then min(T0) is applied
  Then result is T2

Scenario: skull is the lowest tier
  Given any TrustTier t
  When t.min(SKULL) is called
  Then result is SKULL

# Skill registry
Scenario: load_builtins registers at least 9 skills
Scenario: t0 skill cannot be overwritten by a t2 skill
Scenario: list_by_mode returns only skills with the requested mode

# Engine — generate
Scenario: generate returns DesignProject.trust_tier == min of all inputs
Scenario: generate raises DiscoveryIncompleteError for a missing required field
Scenario: generate raises SkillModeError for image-mode skill when image_gen is None
Scenario: Warden-flagged discovery response raises TrustBannedError
Scenario: Every scanned input creates a TrustReviewRecord in the queue

# DAG node
Scenario: DesignOrchestrateNode is registered under kind "design.orchestrate"
```

## Consequences

**Positive**
- Design workflows gain the full security stack (Warden, trust tiers, RLPHD) with no bolting onto canvas.
- Skills are composable by downstream products (Project_mAIstro, stronghold) without engine changes.
- DAG node registration means design steps compose into any existing workflow graph.

**Negative / trade-offs**
- Adds a sixth importable package to the workspace; dependency graph grows.
- `DesignEngine` must be instantiated per-session; no singleton usage. Callers must manage lifecycle.

## Out of scope

- LLM invocation (engine builds the prompt stack; conduit handles the call)
- Frontend / UI for the admin trust-review panel (emits records; UI is a downstream concern)
- Bundled named design systems (open-design's 150 systems); registry + loader only in v0
- Persistence layer for `DesignProject` (in-memory only; PostgreSQL store is v1)
- Multi-tenant isolation (stronghold concern per ADR-019)
