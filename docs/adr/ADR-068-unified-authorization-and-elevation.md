---
id: ADR-068
title: "Unified Authorization & Elevation — one model for who-may, what-class, and human-in-the-loop"
repo: maistro-engine
kind: adr
status: Proposed
created: 2026-05-29
substrate:
  - maistro-engine#ADR-028
  - maistro-engine#ADR-050
  - maistro-engine#ADR-051
  - maistro-engine#ADR-054
related:
  - maistro-engine#ADR-019
  - maistro-engine#ADR-023
  - maistro-engine#ADR-024
  - maistro-engine#ADR-037
  - maistro-engine#ADR-038
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
  - boundary
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# ADR-068: Unified Authorization & Elevation

**Status:** Proposed
**Date:** 2026-05-29
**Amends:** ADR-028 (adds the agent principal + 2FA leg to the elevation flow), ADR-051
(retires the "ADR-028 is orthogonal" framing — they are two axes of one decision),
ADR-019 / Key Design Decision 7 (scope hierarchy: `tenant > org > team > user`)

---

## Context

Four ADRs each own one slice of "may this action run, and does a human need to see it
first," but none states how they compose, and one of them contradicts another:

- **ADR-028 (privilege separation)** — *who* the principal is. A mandatory two-tier
  `admin`/`user` split; privileged operations route through admin via wallet-signed
  elevation. This is **process / identity level**.
- **ADR-050 (reversibility taxonomy)** — *what class* the action is.
  `internal | reversible | irreversible` tag on every tool call. The **classifier** the
  other layers read.
- **ADR-051 (approval gates)** — *whether this specific call* needs a human right now.
  Plan-preview / impact escalation / learned trust. This is **task / runtime level**, and
  its Context explicitly calls ADR-028 *"orthogonal; process-level, not task-level."*
- **ADR-054 (task budgets)** — *whether there is spend left*. A cost/token/step/wall-clock
  ceiling per task that "composes with ADR-051 approval gates."

The result is real ambiguity the implementation already tripped on: the hive-conductor
`_PROTECTED_OPS` middleware had to guess whether a DAG-run POST is an ADR-028 privilege
check, an ADR-051 approval gate, both, or neither — and in what order. "Orthogonal" is not
an evaluation order.

The user's framing is the unifying insight: there is **one set of actions any authenticated
principal may take ambiently**, and **a second set that requires *elevation* in the UI and
*2FA* for agents** — and the DID/wallet identity (ADR-023/024) is what makes the agent-2FA
leg the *same cryptographic act* as a human approving "send 1000 sats." ADR-028's elevation
flow only ever modelled a *human* admin signing; it never modelled an *agent* principal
authenticating its own irreversible call. That gap is why the two layers looked orthogonal.

## Decision

Authorization is **one decision evaluated over three independent axes**, in a fixed order.
The axes are not orthogonal — they are *and*-combined: an action runs only if it passes all
of them.

### The three axes

| Axis | Source ADR | Question | Values |
|------|-----------|----------|--------|
| **Principal** | ADR-028 + scope (ADR-019) | Who is asking, at what scope, with what privilege? | `admin` / `user`; scope `global > org > team > user > agent > session` |
| **Class** | ADR-050 | What is the side-effect nature of the action? | `internal` / `reversible` / `irreversible` |
| **Budget** | ADR-054 | Is there cost/token/step/wall-clock headroom? | within / over |

### Two action bands (the user's "ambient vs guarded" split)

Collapsing principal × class yields exactly two bands:

- **Band A — ambient.** `internal` and `reversible` actions, requested by a principal whose
  scope grants the capability. Run with **no gate**. Available to *any* authenticated user
  **and** to agents acting within their delegated scope. (Examples: read memory, create a
  schedule, run a reversible tool with a registered compensator.)

- **Band B — guarded.** `irreversible` actions, **or** any action requiring a capability
  outside the principal's scope/privilege. These require a **human-in-the-loop signature**
  before execution:
  - **UI principal (human user)** → **elevation**: admin signs via wallet (ADR-022/023),
    OR a time-boxed delegation, OR a standing policy VC (the three ADR-028 modes).
  - **Agent principal** → **2FA**: the agent signs the action with its own DID key
    (ADR-023/024). The signature is the agent's second factor; the HITL gate (ADR-051)
    decides whether a *human* co-signature is additionally required based on impact.

The wallet/DID signature is **one primitive serving both legs** — human elevation and agent
2FA are the same `sign(action)` act, recorded as a VC (ADR-024). This is the property that
makes approval composable across humans and agents.

### Evaluation order (the precedence ADR-051 was missing)

For every tool call / privileged operation, substrate evaluates **in this order** and
**stops at the first denial**:

```
1. CLASSIFY   reversibility tier (ADR-050) + privilege requirement (ADR-028)
              + budget cost estimate (ADR-054). Pure; no side effects.

2. AUTHORIZE  (ADR-028 + scope) Does the principal's privilege + scope grant the
              capability at all?
                • granted        → continue
                • not granted    → require ELEVATION (human) or 2FA (agent).
                                   No signature ⇒ DENY (401/403-equivalent).

3. BUDGET     (ADR-054) Does the call fit the remaining task budget?
                • fits           → continue
                • over           → raise an ADR-051 "approve more budget?" gate; DENY on
                                   refusal. Budget veto cannot be bypassed by elevation.

4. APPROVE    (ADR-051) Only for Band B (irreversible). Run the layered gate:
              plan-preview ∪ impact-escalation ∪ learned-trust. The signature from
              step 2 IS the approval artifact when impact warrants HITL.
                • approved / trusted → EXECUTE
                • denied / timeout   → DENY (+ compensator if mid-saga, ADR-050)
```

Band A actions short-circuit: they pass step 2 (in-scope) and step 4 (not irreversible) with
no prompt, subject only to the step-3 budget check.

### Why order matters

- **Authorize before approve.** A principal who lacks the capability entirely must never
  reach a content-bearing approval prompt — that would leak the action's existence and
  invite social-engineering of the approver. Capability is a structural gate (ADR-028's
  thesis: "structural, not behavioral"); approval is a judgement gate.
- **Budget is a hard veto, not an approvable.** Over-budget raises a gate, but elevation
  cannot *override* a zero balance — only a human explicitly granting more budget can. This
  prevents "just elevate past the ceiling" as an exfiltration path.
- **Reversibility feeds, never decides.** ADR-050 is the classifier the other two axes read;
  it issues no allow/deny itself.

## Scope hierarchy (amends ADR-019 / Key Design Decision 7)

The principal axis needs a scope model, and the existing "no `org_id` in maistro-core" rule
was conflating *scope* with *tenancy*. Corrected hierarchy, narrowest → widest:

```
user  <  team  <  org (a team of teams)  <  tenant
```

- **user / team / org** are **soft scope axes inside a tenant**. A user can belong to
  multiple teams and orgs in the same tenant. `org`/`team` scoping **is legitimate in
  maistro-core** as a scope axis — the engine keeps `global > org > team > user > agent >
  session`.
- **tenant** is the **hard isolation boundary, Stronghold-only**. Tenants are fully
  segmented; a user belongs to exactly one tenant and needs a *separate user* to act in
  another. Core never sees `tenant`.

So Key Design Decision 7 is amended from "no org_id in core" to: *core carries the soft scope
axes (incl. org/team) and global→session isolation; Stronghold adds the hard `tenant`
boundary.* ADR-013/015/016/017 org filters were always correct — the term "org" had simply
been read as "tenant."

## Interface (sketch)

```python
class ActionBand(StrEnum):
    AMBIENT = "ambient"   # Band A
    GUARDED = "guarded"   # Band B

class AuthzDecision(BaseModel):
    band: ActionBand
    authorized: bool                 # step 2
    elevation_required: bool         # human signature needed
    twofa_required: bool             # agent signature needed
    within_budget: bool              # step 3
    approval: ApprovalDecision | None  # step 4 (ADR-051), None for Band A
    reason: str

class AuthorizationService(Protocol):
    def classify(self, call: ToolCall, principal: Principal) -> ActionClass: ...   # ADR-050+028
    async def authorize(self, call: ToolCall, principal: Principal) -> AuthzDecision: ...
    # authorize() runs steps 1-4 in order; raises NOTHING — it returns a decision the
    # caller (Sentinel / route middleware) enforces.
```

The hive-conductor `_PROTECTED_OPS` table is the **first concrete implementation** of step 2
for the HTTP surface: privileged/irreversible routes (containers, dag-run, optimizer,
pm-fleet) map to a required capability; admin passes; a user without elevation gets the
"elevate to proceed" path; an agent presents a signed token. WebSocket handlers enforce the
same `authorize()` because BaseHTTPMiddleware does not run for the websocket scope.

## Acceptance criteria

- [ ] `authorize()` evaluates the four steps in the stated order and short-circuits on first
      deny; property test: no Band-A action ever raises a prompt.
- [ ] A capability outside the principal's scope returns `authorized=False` with
      `elevation_required` (human) or `twofa_required` (agent) — **before** any approval
      prompt is constructed.
- [ ] An over-budget call cannot be executed by elevation alone; only an explicit
      budget-grant clears it.
- [ ] Agent principals satisfy Band B via a DID-key signature (ADR-023/024) recorded as a VC;
      human principals satisfy it via the three ADR-028 elevation modes.
- [ ] A single signed-VC artifact serves both the ADR-028 elevation record and the ADR-051
      `ApprovalDecision.decided_by`.
- [ ] hive-conductor: privileged HTTP routes AND the matching WebSocket handlers both call
      `authorize()`; unauthenticated WS connections are closed (1008) before accept.
- [ ] Audit: every Band-B grant/denial/expiry recorded as a signed VC (ADR-024, ADR-037).

## Consequences

- ADR-051's Context line "ADR-028 ... orthogonal" is **superseded** by this ADR: they are
  the *authorize* and *approve* steps of one ordered evaluation.
- ADR-028's elevation flow gains an **agent principal** with a 2FA leg; the human flow is
  unchanged.
- ADR-019 / Decision 7 are amended for the scope hierarchy (separate doc edit in this PR).
- Downstream: the staged hive-conductor security cluster (WS auth, hyperlight fail-closed,
  audit anti-spoof, `_PROTECTED_OPS` gating) now has a canonical model to implement against,
  and its previously-failing tests should assert the *documented* model (privileged ops are
  admin's domain / require elevation), not the pre-model open behavior.

## Out of scope

- The notification channel for approval prompts (product-level, per ADR-051).
- The on-disk schema of the learned-trust and elevation-grant stores.
- Multi-tenant (`tenant`) isolation mechanics — Stronghold (ADR-019).
- Full RBAC beyond admin/user + scope axes (ADR-028 out-of-scope still holds).
