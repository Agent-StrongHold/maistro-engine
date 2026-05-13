---
id: SPEC-003
title: "Secrets migration — move plaintext secrets to the vault backend"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-03-23
substrate:
  - maistro-engine#ADR-028
implements:
  - Project_mAIstro#S-109
related: []
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
tests: []
layer: Foundation
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-003: Secrets Migration

## Problem

Some secrets are still stored as environment variables or plaintext in config files. The correct vault backend depends on the product SKU:

- **Agent Conductor** (household/personal) — SPEC-011 age-encrypted file vault, unlocked by admin keypair derived from the Conductor Seed. Secrets belong in `~/.conductor/secrets.age`; accessed via `secrets.use(name, callback)`.
- **Agent Stronghold** (multitenant) — Vaultwarden API. Secrets read from Vaultwarden at startup.

## Acceptance Criteria

- [ ] Zero plaintext secrets in any tracked config file or `.env` file; `gitleaks` pre-commit hook passes on all tracked files with no suppressions
- [ ] All API keys, passwords, tokens, and connection strings are accessed via `secrets.use()` from the appropriate vault backend
- [ ] Conductor fails closed at startup when a required secret is absent from the vault: conductor logs `SECRET_MISSING` naming the missing key and exits; it does not start in a degraded mode
- [ ] Migration is idempotent: re-running the migration process does not duplicate vault entries or produce errors on subsequent runs
- [ ] Any secret that was ever in git history has been rotated in the vault (old value is no longer valid at the upstream service)
- [ ] `gitleaks` scan covers full git history, not only the working tree
