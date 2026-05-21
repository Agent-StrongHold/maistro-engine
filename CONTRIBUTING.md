# Contributing to maistro-engine

Author-facing summary of the conventions you need to know to land changes here. Each rule has an ADR or spec — this page links to the source of truth, doesn't duplicate it.

## Branch model

`feature/* → integration → main`. Integration is the QA tier. Feature branches base off integration. Detail: [`docs/adr/ADR-001-branching-strategy.md`](docs/adr/ADR-001-branching-strategy.md).

## How to add an ADR

1. Copy [`docs/adr/ADR-000-template.md`](docs/adr/ADR-000-template.md) to `docs/adr/ADR-NNN-kebab-title.md`. NNN is the next free number — check the directory listing.
2. Fill in the YAML front-matter block. Schema and required fields are in [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md).
3. Write the body. ADRs are short — context, decision, consequences, status. Keep it under one screen if you can.
4. If your decision has cross-repo implications, use `<repo>#<id>` references (e.g. `AgentTuring#turing-001`). The registry resolves these.
5. Add an entry to [`BACKLOG.md`](BACKLOG.md) under the right milestone if implementation work follows. The BACKLOG is the four-repo canonical — your edit lands identically in all four repos.

Status lifecycle: `Proposed → Accepted → Implemented → Superseded`, plus `Blocked` and `Abandoned`. Per `ADR-031`.

## How to add a spec

Specs are heavier than ADRs — they carry acceptance criteria. Same front-matter schema as ADRs but with `kind: spec`. Specs go in the relevant product repo, not engine, **unless** the spec is engine-level substrate. Use `Substrate: [maistro-engine#ADR-NNN]` to pin a product spec to engine substrate.

Detail: [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md) §front-matter, [`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md) §contracts.

## How to cite substrate

Use `<repo>#<id>` in references. Valid repos: `maistro-engine`, `Project_mAIstro`, `AgentTuring`, `stronghold`. Examples:

- `[engine#ADR-036]` — engine architectural decision
- `[turing#turing-001]` — AgentTuring backlog item
- `[sh#ADR-010]` — stronghold ADR

The registry validates these — every reference must resolve to an existing record.

## Layered contracts (acceptance criteria)

Three layers per [`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md):

1. **Pydantic boundary** — at every public type, validate inputs/outputs structurally. `extra=forbid`. JSON Schemas auto-generated for stable wire types.
2. **Hoare behavioral** — Hypothesis property tests for accepted behavioral ADRs. Pre/post conditions encoded.
3. **Pact-style cross-service** — consumer-driven contracts on A2A and MCP edges. (Tooling: TBD per `engine-080`.)

Mutation-test kill rates are the v1.0 quality bar. Targets per layer in `ADR-032`.

## Adopting external libraries

Anything that lands as a dependency goes through [`ADR-039`](docs/adr/ADR-039-external-library-adoption-policy.md). Four outcomes:

- **Import** — peer products may import if maintainer-signal gate passes (org backing, activity, license, contributors). Stronghold is anti-import; uses service-boundary instead.
- **Service-boundary** — separate process, talked to over MCP / HTTP / subprocess. No code dependency.
- **Pattern reference** — borrow the idea, write our own. Record in [`INSPIRATIONS.md`](INSPIRATIONS.md).
- **Reject** — reasons captured.

Stronghold's anti-import posture is a supply-chain stance. The rest of the repos import only when they can't do better/cheaper/faster/more securely themselves.

## Validation

The registry CLI lints front-matter, resolves cross-repo refs, and checks the supersedes/blocks DAG for cycles:

```bash
python -m tools.registry.cli walk docs/adr docs/specs   # dump every record
python -m tools.registry.cli lint docs/adr docs/specs   # validate
python -m tools.registry.cli generate docs/adr docs/specs registry/  # emit registry.json + registry.md
```

CI runs `lint` in warn-only mode currently. Hard-fail flips after day 30 of registry adoption (per `engine-001`).

## Tests

Markers (per [`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md)):

- `@pytest.mark.contract` — boundary-layer Pydantic tests
- `@pytest.mark.behavioral` — Hypothesis property tests on ADR invariants
- `@pytest.mark.scope(...)` — scope marker for test-tier partitioning

Run `pytest -m contract` for fast boundary tests; `pytest -m behavioral` for property tests.

## Commit style

Imperative mood, one logical change per commit. PR titles include the backlog id when relevant: `engine-NNN: short description`. PR body explains the *why*; the diff explains the *what*.

## Pre-merge checklist

- [ ] ADR or spec landed (or referenced) for non-trivial decisions
- [ ] Front-matter present (registry CI green)
- [ ] Tests at the right layer per `ADR-032`
- [ ] Cross-repo refs resolve
- [ ] BACKLOG entry status updated if shipping closes one

## Where to ask

Open a draft PR early. Decisions land in ADRs, not chat.
