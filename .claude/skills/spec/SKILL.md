---
name: spec
description: Scaffold a new SPEC design doc in docs/specs/. Produces strict front matter validated by maistro-registry (id, title, repo, kind, status, created, layer, owners, relationships). Pass a short title as the argument, e.g. /spec capability-budgeting
disable-model-invocation: false
---

The user wants to create a new SPEC. The argument is $ARGUMENTS (the short title/slug).

Front matter is machine-validated by maistro-registry (`extra = forbid` — unknown or missing fields fail). Get it exactly right.

Steps:
1. Run `ls docs/specs/ | sort | tail -3` to find the highest SPEC number on this branch.
   IMPORTANT: also check numbers claimed by other open PR branches, or you will collide with
   an in-flight spec the local tree can't see:
   `for n in $(gh pr list --state open --json number -q '.[].number'); do gh pr view $n --json files -q '.files[].path'; done | grep -oE 'SPEC-[0-9]+' | sort -u | tail`
2. Compute the next number above ALL of those, zero-padded to 3 digits (e.g. SPEC-201). The id MUST match `^SPEC-\d{3}$`.
3. Convert $ARGUMENTS to kebab-case for the filename slug → `docs/specs/SPEC-NNN-<slug>.md`.
4. Use today's date from the environment for `created` (YYYY-MM-DD). Do NOT guess.
5. Write the file with this exact front-matter shape, filling in real values:

```markdown
---
id: SPEC-NNN
title: "<one-line title>"
repo: maistro-engine
kind: spec
status: Proposed
created: <YYYY-MM-DD>
substrate: []        # ADRs/SPECs this builds on, e.g. maistro-engine#ADR-031
implements: []       # ADRs this realizes
related: []          # loosely related, e.g. maistro-engine#SPEC-184
supersedes: []
blocks: []
blocked-by: []       # note: hyphen in YAML key
contracts: []        # any of: boundary, behavioral, cross-service
tests: []
layer: <Layer>       # see valid values below (Evolve/Crypto/Connectivity/Ability per ADR-098)
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-NNN: <Title>

## Context

<What problem / situation motivates this spec?>

## Goals

-

## Non-goals

-

## Decision

<The design. Interfaces, data shapes, control flow.>

## Acceptance criteria

-

## Testing

<How this is verified — unit, integration, formal invariants.>

## Open questions

-

## References

-
```

Field rules (enforced by the schema):
- `status` ∈ {Proposed, Accepted, Implemented, Superseded, Blocked, Abandoned} — new specs start `Proposed`.
- `layer` ∈ {Foundation, Orchestration, Agents, Tools, Memory, Observability, Reliability, Governance, UserClient, Evolve, Crypto, Connectivity, Ability}. Scope definitions for the last four are in ADR-098. Pick the best fit; ask the user if unclear.
- `contracts` entries ∈ {boundary, behavioral, cross-service}.
- Cross-references use the form `maistro-engine#ADR-NNN` or `maistro-engine#SPEC-NNN`.
- Empty lists are valid; omit no keys (every field is required).

6. After writing, validate it:
   ```bash
   PYTHONPATH=packages/maistro-registry/src python3 -m maistro_registry.cli validate docs/specs/SPEC-NNN-<slug>.md
   ```
   Fix any reported errors before finishing.
7. Show the user the created path and remind them to flip `status: Proposed → Accepted` once agreed, and to fill `implements`/`tests` as work lands.
