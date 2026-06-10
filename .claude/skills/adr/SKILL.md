---
name: adr
description: Scaffold a new Architecture Decision Record in docs/adr/. Follows the existing ADR-NNN-slug.md naming convention and the ADR-031 front-matter schema (validated by maistro-registry; registry CI is strict). Pass a short title as the argument, e.g. /adr graph-caching-strategy
disable-model-invocation: false
---

The user wants to create a new ADR. The argument is $ARGUMENTS (the short title/slug).

Front matter is machine-validated by maistro-registry (`extra = forbid` — unknown or missing fields fail), and registry CI runs strict (warnings are failures). Get it exactly right.

Steps:
1. Run `ls docs/adr/ | sort | tail -3` to find the highest ADR number on this branch.
   IMPORTANT: also check numbers claimed by other open PR branches, or you will collide with
   an in-flight ADR the local tree can't see (list open PRs' changed files and grep for `ADR-[0-9]+`).
2. Compute the next number above ALL of those, zero-padded to 3 digits (e.g. ADR-099). The id MUST match `^ADR-\d{3}$`.
3. Convert $ARGUMENTS to kebab-case for the filename slug → `docs/adr/ADR-NNN-<slug>.md`.
4. Use today's date from the environment for `created` (YYYY-MM-DD). Do NOT guess.
5. Create the file with this template, filling in real values:

```markdown
---
id: ADR-NNN
title: "<one-line title>"
repo: maistro-engine
kind: adr
status: Proposed
created: <YYYY-MM-DD>
substrate: []        # ADRs/SPECs this builds on, e.g. maistro-engine#ADR-031
implements: []
related: []
supersedes: []
blocks: []
blocked-by: []       # note: hyphen in YAML key
contracts: []        # any of: boundary, behavioral, cross-service
tests: []
layer: <Layer>       # one of: Foundation, Orchestration, Agents, Tools, Memory, Observability, Reliability, Governance, UserClient, Evolve, Crypto, Connectivity, Ability (last four per ADR-098)
owners:
  - '@BlakeMatthews-dev'
---

# ADR-NNN: <Title>

## Context

<What is the situation that motivates this decision?>

## Decision

<What is the change we're making?>

## Consequences

### Positive
-

### Negative / Trade-offs
-

### Neutral
-
```

6. After writing, validate it:
   ```bash
   PYTHONPATH=packages/maistro-registry/src python3 -m maistro_registry.cli validate docs/adr/ADR-NNN-<slug>.md
   ```
   Fix any reported errors before finishing.
7. Show the user the created file path and remind them to update the status (Proposed → Accepted) once agreed.
