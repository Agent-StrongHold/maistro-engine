---
id: S-153
title: "Networking & identity substrate — Tailscale recommended, mesh substrates pluggable"
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

# S-153: Networking & Identity Substrate

## Acceptance Criteria

- [ ] Conductor's networking layer is implemented as a substrate abstraction; no conductor code references any specific substrate directly
- [ ] All eight substrates (Tailscale, Headscale, NetBird, ZeroTier, Cloudflare Tunnel, LAN-mDNS, localhost-only, manual) can be selected at setup time and reconfigured later without reinstall
- [ ] On Tailscale-paired install: dashboard reachable at `https://<instance>.<tailnet>.ts.net` within 60 seconds, with valid auto-issued cert
- [ ] On ZeroTier: dashboard reachable on ZT IP; admin authenticates via S-149 keypair challenge; non-ZT-member machines cannot connect
- [ ] ZeroTier identity enforcement: a ZeroTier-network member with a valid ZT IP but without a valid S-149 challenge-response receives `401 Unauthorized` from the conductor; presenting a valid ZT network address alone is not sufficient for any access level (admin or user); the challenge-response signature is verified against the configured admin/user public keys before any request proceeds
- [ ] On localhost-only: dashboard reachable on `127.0.0.1`; admin authenticated via Unix socket peer credentials
- [ ] Substrate switch is recoverable: an operator can move between any pair of substrates by editing the config and restarting; conductor picks up the change
- [ ] No substrate is required for the conductor to start; localhost-only is always a valid configuration

See `blakematthews-dev/project_maistro` specs/infra/S-153-tailscale-native.md for full spec.
