---
id: S-158
title: "Human-as-node delegation — channel-routed prompts, identity-attested replies, per-human prompt optimization"
domain: conductor
status: draft
priority: P1
effort: ""
created: 2026-04-25
completed: ""
owner: conductor
commits: []
supersedes: ""
---

# S-158: Human-as-Node Delegation

## Acceptance Criteria

- [ ] A `human` node can be added via S-159 Node Designer with at least 5 channel options (Teams, email, SMS, conductor, conductor-app)
- [ ] Channel selection respects priority + hours + urgency policy; verified by browser automation
- [ ] Reactor registers wait-events on channel responses; timeout falls back to next-priority channel; exhaustion produces a structured "no human response" error
- [ ] Bouncer screens human responses on return; verified with a test that injects a known prompt-injection payload into a simulated human reply
- [ ] Audit log records every human delegation as a signed VC with channel, latency, identity attestation method, response
- [ ] Privacy-tagged delegations store hashed responses in the public VC and cleartext only in operator-encrypted side-channel
- [ ] Per-human prompt optimization (opt-in) converges on per-human variants over time; verified with simulated Jenny (varying response quality by variant) yielding stable optimal-variant after N delegations
- [ ] Opt-out: `STOP-LEARN` reply disables optimization for that human and deletes variant-performance state
- [ ] Federation case: Conductor A delegates to Jenny via Conductor B; both conductors record the delegation; A learns its own framing without B sharing its variant scores
- [ ] SMS / cost-bearing channels require admin signature before each delegation
- [ ] Higher-trust intents (signing, financial) refuse lower-trust channels (email, SMS) per intent policy
- [ ] Delegation rate limits: defaults set during setup wizard (S-139), stored per-node in config, enforced at delegation dispatch; `DELEGATION_RATE_LIMIT_EXCEEDED` returned to requesting node when a cap is hit (not a silent drop)
- [ ] First contact: the first delegation to a new human node includes a STOP-LEARN opt-out marker in the message; `STOP-LEARN` reply on any channel disables per-human optimization and deletes variant-performance state; no pre-consent gate is required before the first message

See `blakematthews-dev/project_maistro` specs/conductor/S-158-human-as-node.md for full spec.
