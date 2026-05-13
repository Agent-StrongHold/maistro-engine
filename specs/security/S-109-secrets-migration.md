---
id: S-109
title: "Secrets migration — move plaintext secrets to the vault backend"
domain: security
status: draft
priority: P1
effort: "2 hours"
created: 2026-03-23
completed: ""
owner: conductor
commits: []
---

# S-109: Secrets Migration

## Problem

Some secrets are still stored as environment variables or plaintext in config files. The correct vault backend depends on the product SKU:

- **Agent Conductor** (household/personal) — S-141 age-encrypted file vault, unlocked by admin keypair derived from the Conductor Seed (S-149). Secrets belong in `~/.conductor/secrets.age`; accessed via `secrets.use(name, callback)`.
- **Agent Stronghold** (multitenant) — S-023 Vaultwarden API. Secrets read from Vaultwarden at startup.

This spec tracks migration of existing plaintext secrets to whichever backend is in use. The `secrets.use()` API is the same in both cases; only the backend differs.

## Acceptance Criteria

- [ ] Zero plaintext secrets in any tracked config file or `.env` file; `gitleaks` pre-commit hook passes on all tracked files with no suppressions
- [ ] All API keys, passwords, tokens, and connection strings are accessed via `secrets.use()` from the appropriate vault backend (S-141 for Agent Conductor; S-023 Vaultwarden for Agent Stronghold)
- [ ] Conductor fails closed at startup when a required secret is absent from the vault: conductor logs `SECRET_MISSING` naming the missing key and exits; it does not start in a degraded mode with the missing credential silently unavailable
- [ ] Migration is idempotent: re-running the migration process does not duplicate vault entries or produce errors on subsequent runs
- [ ] Any secret that was ever in git history has been rotated in the vault (old value is no longer valid at the upstream service)
- [ ] `gitleaks` scan covers full git history, not only the working tree
