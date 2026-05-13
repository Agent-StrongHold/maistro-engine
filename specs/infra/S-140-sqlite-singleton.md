---
id: S-140
title: "SQLite singleton writer — the invariant that protects state under the reactor"
domain: infra
status: draft
priority: P1
effort: ""
created: 2026-04-25
completed: ""
owner: conductor
commits: []
supersedes: ""
---

# S-140: SQLite Singleton Writer

## Acceptance Criteria

- [ ] Conductor process opens exactly one SQLite write-mode connection across its lifetime
- [ ] `open_writer()` raises if called more than once; `open_reader()` returns read-only connections
- [ ] CI gate fails the build if any production code opens SQLite in non-`ro` mode outside the singleton module
- [ ] All subsystem writes route through `state.submit(transaction)`
- [ ] Queue is bounded; overflow applies backpressure (submit blocks) rather than dropping or OOMing
- [ ] Concurrent reads from many subsystems + Console + external `sqlite3` CLI work without contention while the writer is active
- [ ] WAL checkpoint runs periodically; database file does not grow unboundedly
- [ ] Conductor crash: SQLite state remains consistent; in-flight queue entries are lost (documented; subsystems that need durability journal first)
- [ ] State database backups are encrypted with the admin keypair (S-141-style age encryption) before writing to disk; no plaintext copy of `state.db` is ever written to `~/.conductor/backups/`; backup files use the `.db.age` suffix and are importable via `maistro db restore`
- [ ] Schema migrations run atomically at startup; a failed migration rolls back completely and conductor refuses to start with a `MIGRATION_FAILED` error naming the failing migration; conductor never starts with a partially-migrated schema
- [ ] Migration path to libSQL / Turso documented (drop-in upgrade for replication)

See `blakematthews-dev/project_maistro` specs/infra/S-140-sqlite-singleton.md for full spec.
