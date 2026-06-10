---
id: SPEC-206
title: Policy-conformance comparison engine — ADRs → Specs → prior policy
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-05-30
accepted: null
implemented: null
substrate:
  - maistro-engine#ADR-074
  - maistro-engine#ADR-031
  - maistro-engine#ADR-032
implements:
  - maistro-engine#ADR-074
related:
  - maistro-engine#ADR-068
  - maistro-engine#ADR-070
  - maistro-engine#ADR-073
contracts:
  - boundary
  - behavioral
tests: []
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-206: Policy-conformance comparison engine

**Implements:** ADR-074 (Policy ⇄ ADR Deconfliction). ADR-074 decides *what to do on conflict*; this
spec defines *how a conflict is detected* — the comparison engine and its precedence walk.

---

## Problem

ADR-074 requires that a candidate policy decision be compared against authorities in strict precedence
(ADRs → Specs → prior policy) before it can commit (the Repertoire *Rehearse* gate, ADR-070). That
requires a concrete engine: how each layer's invariants are represented, how "conflict" is computed
per layer, and how the result routes into ADR-074's three outcomes.

## Decision

### Authorities carry machine-checkable invariants

For the engine to compare against an ADR or Spec, the authority must expose **checkable assertions**,
not just prose. Extend the registry front-matter (ADR-031/032) with an optional `invariants:` block:

```yaml
# in an ADR/Spec front-matter
invariants:
  - id: INV-068-budget-veto
    safety_critical: true
    assert: "no policy permits a tool call whose cumulative_spend would exceed the task budget"
    check: "code-registry-ref:policy.checks.budget_veto@v1"   # ADR-069 ref, microVM-run
```

- `safety_critical: true` marks an invariant ADR-074 treats as near-inviolable (drift → security review).
- `check` is a **code-registry ref** (ADR-069) — a verifier run in a microVM that returns
  `{satisfied: bool, witness?}` for a candidate policy. Prose-only invariants (no `check`) are
  flagged for human review rather than auto-checked.

### The precedence walk

```python
class Authority(StrEnum):
    ADR = "adr"; SPEC = "spec"; PRIOR_POLICY = "prior_policy"

class ConformanceVerdict(BaseModel):
    ok: bool
    conflict_layer: Authority | None          # first layer that conflicted (None if ok)
    conflict_ref: str | None                   # e.g. "maistro-engine#ADR-068 / INV-068-budget-veto"
    safety_critical: bool = False
    artifacts: list[str] = []                  # N deployed artifacts also in conflict
    evidence: dict                             # the learning's rationale (for the impact analysis)

class ConformanceEngine(Protocol):
    async def check(self, candidate: PolicyDecision) -> ConformanceVerdict: ...
```

`check()` walks **in order, stopping at the first conflict**:

1. **ADRs** — evaluate every relevant ADR invariant whose `check` ref applies to `candidate`.
   Conflict → return with `conflict_layer=ADR`, `safety_critical` from the invariant. (Stop.)
2. **Specs** — same, over Spec invariants. Conflict → `conflict_layer=SPEC`. (Stop.)
3. **Prior policy** — query the policy/audit store (ADR-073 DB, the decision log) for prior decisions
   on the same `(action, scope)` that the candidate would reverse. Conflict → `conflict_layer=
   PRIOR_POLICY` with the superseded precedent in `conflict_ref`. (Stop.)

Relevance is by **scope + action class** (an invariant/precedent applies if its subject overlaps the
candidate's `(action, for-scope, reversibility)`), so the engine checks a bounded set, not the whole
corpus.

### Routing into ADR-074 outcomes

- `ok == true` → the candidate passes Rehearse → **Compose/commit** (ADR-070).
- `conflict_layer != None` → **held**; hand the verdict (layer, ref, artifacts, evidence) to the
  ADR-074 admin review. If `safety_critical` → route to the **security** review path (default revert).

### Artifact blast-radius

When a conflict is found, the engine also resolves the **N deployed artifacts** that depend on the
conflicting authority (recipes citing the ADR via `substrate:`, active policies, code-registry refs),
so the "amend + reconcile" outcome has the exact list to update. This reuses the registry's existing
cross-ref graph (ADR-031).

## Acceptance criteria

- [ ] `check()` walks ADR → Spec → prior-policy and **returns on the first conflict** (property test:
      a candidate conflicting with both an ADR and a Spec reports `conflict_layer=ADR`).
- [ ] An invariant with `safety_critical: true` sets the verdict flag, routing ADR-074 to security review.
- [ ] Invariant `check` refs execute as ADR-069 code-registry verifiers (signed, microVM); an
      unresolved/unsigned check fails closed (treated as conflict pending review).
- [ ] Prose-only invariants (no `check`) are surfaced for human review, never silently passed.
- [ ] Relevance filtering bounds the check to invariants/precedents overlapping the candidate's
      `(action, scope, reversibility)`.
- [ ] A conflict verdict includes the N deployed artifacts depending on the conflicting authority
      (from the ADR-031 cross-ref graph).
- [ ] `ok` candidates pass to the ADR-070 Compose/commit path; conflicting ones are held.
- [ ] Every `check()` result is logged (ADR-037 `policy.decision`) for audit and predictor feedback.

## Out of scope

- The admin-review UI / workflow — product surface (ADR-074 defines the outcomes).
- Authoring the invariant `check` verifiers themselves — per-ADR, code-registry entries.
- Backfilling `invariants:` onto existing ADRs — incremental; this spec defines the mechanism, not the
  migration. Safety-critical ADRs (ADR-072/028/068) get invariants first.
