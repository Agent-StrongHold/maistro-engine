---
id: S-154
title: "Electrum server — Medley plugin for household-private Bitcoin backend"
domain: tools
status: draft
priority: P2
effort: ""
created: 2026-04-25
completed: ""
owner: conductor
commits: []
supersedes: ""
---

# S-154: Electrum Server Plugin

## Acceptance Criteria

- [ ] `medley install electrum-server` brings up bitcoind + electrs as supervised services
- [ ] Initial sync completes and dashboard reflects accurate progress throughout
- [ ] Conductor's wallet (S-151) automatically uses the local backend once sync is current
- [ ] Lightning plugin (S-151) detects and uses the local Bitcoin node when both are installed
- [ ] Household phone wallets (Sparrow, BlueWallet, Phoenix, Zeus, Mutiny) successfully connect using the documented endpoint
- [ ] Tailnet-private exposure is the default; public exposure is not offered through normal config flow
- [ ] Plugin survives conductor restart with no data loss; bitcoind and electrs come back to a consistent state
- [ ] RPC credentials and TLS material are stored in the S-141 vault, never in plaintext config files visible to other plugins
- [ ] Resource caps (memory, bandwidth) are enforced via the substrate's per-plugin sandboxing (S-148 container path) or systemd cgroups (S-147 native path)
- [ ] Phantom Execution (S-030) verifies plugin behavior on signet before mainnet promotion
- [ ] Pre-sync snapshot import is offered as an option with explicit "trust this publisher" gate
- [ ] `medley update electrum-server` follows the ordered stop/update/restart sequence; wallet falls back to public endpoint during the update window; failed update rolls back to previous binaries and posts to board
- [ ] Chain data backup policy is documented in `medley info electrum-server`: chain data is NOT vault-backed; re-sync is the recovery path; only vault credentials require backup
- [ ] Port conflict detection: if the configured Electrum TLS port (default 50002) is already in use at install time, the install fails with a clear error message and directs the operator to set `electrum_rpc_tls_port` in plugin config

See `blakematthews-dev/project_maistro` specs/tools/S-154-electrum-server.md for full spec.
