---
id: S-145
title: "Hyperagent Graph Runtime — the conductor is a self-improving graph of AgentSpec nodes"
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

# S-145: Hyperagent Graph Runtime

## Acceptance Criteria

- [ ] `AgentSpec` is named in the codebase as the canonical node type; no other type fills the role
- [ ] All node invocations pass through the Bouncer at every incoming edge — verified by audit log
- [ ] All long-term graph state mutations are owned by exactly one subsystem from the §4 list, enforced in code review
- [ ] Shape A has at least four working implementations: Claude SDK, LiteLLM-routed plain chat, a Medley-imported skill, **and a human-on-channel node (S-158)**
- [ ] An external multi-agent system (LangGraph or CrewAI) can be imported as a Shape-B subgraph with no Maistro core code changes
- [ ] Dashboard Intel tab (S-016) renders the graph: nodes, recent edges, recent self-improvement events, with replay
- [ ] Self-improvement subsystem registry is enumerated in code (one place, not scattered) and matches the table in §4
- [ ] Initiator identity propagates correctly through chains; verified by audit-log inspection (every VC in a chain has the same `initiator` field)
- [ ] Recursion: a deliberately recursive A→B→A composition completes within budgets; an unbounded version fails at budget exhaustion with a structured error, not at handshake
- [ ] Test: a malicious imported agent (or a malicious human response) cannot escape its capability envelope (verified by adversarial test)
- [ ] Cross-conductor token spend: B's federation response includes `tokens_consumed`; A debits the amount against the chain budget before proceeding; missing field triggers the conservative `ceil(len(response) / 4)` estimate; per-hop spend visible in the chain audit log

See `blakematthews-dev/project_maistro` specs/conductor/S-145-hyperagent-graph-runtime.md for full spec.
