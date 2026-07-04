# Mining inventory — stronghold / AgentTuring / A2UI → maistro-engine

**Status:** first-wave (Opus) reports complete; Haiku line-level sweep S01–S17 **complete**
(see `reports/S*.md`, 2.9k lines of findings).
**Scope:** product-agnostic only (ADR-019/035). Enterprise/multi-tenant/K8s/coin-economy = skip.
**Baseline:** maistro-engine has 112 ADRs, 142 specs; date-based ID scheme (ADR-062026-9b30).

Deconfliction rule that gates everything: engine **ADR-019** puts multi-tenancy/security-posture
in the importing product; engine **ADR-035** puts the multi-tenant catalogs + K8s ADRs in
Stronghold. Many apparent "regressions" (dropped `org_id`, coin economy, K8s, OIDC) are
by-design drops, not accidents.

---

## GROUP A — Additive ADRs/specs (Wave 1, land first; zero runtime risk)

| # | Item | Source | Engine gap | Action | Effort |
|---|---|---|---|---|---|
| A1 | **A2UI protocol adoption** | A2UI whole repo | BACKLOG `[engine-090/091]` + `[sh-602]` commit to it; SPEC-179 references it; never formalized | ADR + SPEC | L |
| A2 | **COMPLIANCE.md** (OWASP-Agentic / NIST AI RMF / EU AI Act / SOC2 → control→test matrix) | stronghold/COMPLIANCE.md | engine has controls, no mapping doc (grep: 0 OWASP/NIST hits) | new doc/ADR | M |
| A3 | **SECURITY.md** (defense-in-depth layers + resource-limit inventory + honest-limitations) | stronghold/SECURITY.md | no SECURITY.md in engine | new doc | M |
| A4 | **CapabilityProfile** `(capability,intent)→(permission,skill_score EMA,cost_vector)` | epic-02 | none; SPEC-184 is a different axis | ADR + SPEC | M |
| A5 | **Substrate / light-vs-heavy agent taxonomy** (light agents hold zero tools) | epic-04 | none structural | ADR | M |
| A6 | **Six-tier priority system** P0–P5 (routing weight, model bias, token mult, eviction) | ADR-K8S-014/015 (de-K8s'd) | only coarse LIVE/BACKGROUND (ADR-010) | ADR | M |
| A7 | **Session Trust Floor** — monotonic per-session trust reducer; `WardenVerdict.confidence` | BACKLOG CFM-2 | only upward elevation ladders (ADR-068) | ADR + SPEC | L |
| A8 | **Autonoetic self-model threat model + guardrails G1–G18** | AgentTuring AUDIT-self-model-guardrails | none | ADR + SPEC + review doc | M |
| A9 | **RCA structured-output taxonomy** (+`rca_prevention`, outcome loop) | rca-structured-output.yaml | `RCAExtractor` exists — confirm delta | SPEC | M |
| A10 | **Warden L3 redirect-not-refuse + 8-cat attack taxonomy** (+legit negatives) | blue-team-training-spec | L3 is classifier, no redirect posture | ADR + SPEC | L |
| A11 | **Assertion-strength CI gate** (WEAK/BAD/GOOD + LLM-judge + spec-is-gate) | test-quality-audit | SPEC-205 partial | SPEC | M |
| A12 | **Originating-principal transitive-escalation** invariant | epic-03 | ADR-058 checks immediate chain only | SPEC + formal | S |
| A13 | **Self-editing memory tool** (agent-initiated writes, scoped) | epic-12 | extraction-only | SPEC on ADR-057 | M |
| A14 | **Eval substrate** (behavioral span-tags + holdout split + eval-report) | epic-01 | SPEC-202 is evolve-scoped | SPEC | M |
| A15 | **Group-chat / debate / committee patterns** + pattern registry | epic-11 | only parallel waves | SPEC | M |
| A16 | **Meta-optimization loop + self-mutation circuit-breaker** | epic-13 | task-level RSI only | ADR + SPEC | L |
| A17 | MCP resources primitive · task-acceptance policy · hybrid-execution model · SEC-NNN ledger practice | ADR-K8S-023/030/013, SECURITY_FINDINGS | concept-notes | note/ADR | S–M |

## GROUP B — Genuine security-hardening regressions (Wave 2; restore working+tested code)

| # | Item | Source:line | Engine status | Effort |
|---|---|---|---|---|
| B1 | Global payload-size 413 middleware | api/middleware/__init__.py:16 (tested) | webhook-route only | S–M |
| B2 | Cross-model LLM fallback + `/v1/models` discovery | api/litellm_client.py:27 (heavily tested) | same-model retry + breaker | M–L |
| B3 | Security-headers middleware (HSTS/XFO/nosniff/Referrer/Permissions) | api/middleware/security_headers.py:24 | absent everywhere | S |
| B4 | Per-user rate limiting + login brute-force carve-out + `X-RateLimit-*` | api/middleware/rate_limit.py:44 | per-IP only, /health-exempt | M |
| B5 | CSRF header defense on state-changing POSTs | auth.py:43, sessions.py:19 (tested) | none | S |
| B6 | Session ownership + path-traversal ID validation (org-scope axis) | sessions.py:19-115 (tested) | hive chat: no ownership check | M |
| B7 | Demo-cookie → Authorization ASGI injection wiring | api/middleware/demo_cookie.py:20 (tested) | provider in core, unwired | M |

## GROUP C — Net-new code ports (Wave 3; product-agnostic, generalize tenant→scope)

| # | Item | Source | Target | Effort |
|---|---|---|---|---|
| C1 | Redis cache tier: RedisSessionStore, RedisRateLimiter, RedisPromptCache, redis_pool | cache/* | sessions/, security/, cache/ | S–M |
| C2 | Resource Catalog (URI-addressable + credential injection + scope isolation) | resources/catalog.py | maistro/resources/ | M |
| C3 | MCP managed layer: types, MCPRegistry+KNOWN catalog+image allow-list, registries aggregation+scanner | mcp/{types,registry,registries}.py | maistro/mcp/ | M–L |
| C4 | MCP OAuth 2.1 server (store→core, endpoints→server) | mcp/oauth/* | maistro/mcp/oauth + maistro-server | M |
| C5 | Sandbox budgets (SandboxBudgetEnforcer) + SecurityProfile/6 templates | sandbox/{budgets,catalog}.py | maistro/sandbox/ | S–M |
| — | SKIP: K8sDeployer, MCPDeployerClient sidecar (protocol only) | mcp/deployer.py, sandbox/deployer.py | Stronghold | — |

## GROUP D — Builder-pipeline agent DATA + HITL

- D1: Port SOUL.md + agent.yaml for Herald, Quartermaster, Archie, Mason (8-phase TDD YAML),
  Auditor (proactive cron + `pr.opened`), Master-at-Arms, Arbiter, Ranger, Fabulist, Default +
  shared `PREAMBLE.md`. Engine has code strategies, no data. (M, de-tenant)
- D2: Review Queue Engine SPEC — typed `ReviewItem.kind` + priority calculator. (M–L)

## GROUP E — maistro-turing design layer

- E1: ~130 per-concept design specs (`research/project-turing/specs/*.md`) + TRACEABILITY → `docs/specs/turing/`
- E2: HEXACO-200 seed + norms data assets
- E3: Autonoetic thesis / Tulving anchor → short "why" ADR
- E4: 22 Tranche-11 "autonoetic blends" → `docs/research/` digest
- E5: turing-obsidian-store / memory-consolidator / self-talk-loop / dossier-drift specs

## GROUP F — Haiku line-level sweep results (S01–S17)

**At/above parity (no action):** warden (S01 — engine ahead: overlapping scan windows, extra
exfil patterns), skills marketplace/forge (S04 — engine superset), pii/ratelimit/auth (S03),
classifier/router/scheduling (S12 — cost normalization is a deliberate redesign, nothing
dropped), persistence/quota (S09), memory consolidation (S08 — engine ahead), agent strategies
(prior wave — clean port).

**New actionable gaps found by the sweep:**

| # | Item | Slice/report | Severity | Effort |
|---|---|---|---|---|
| F1 | Gate `_check_sufficiency()` is a 2-line stub vs stronghold's 271-line request-sufficiency analyzer (task-signal patterns, confirmation detection, confidence) | S02 | partial | M |
| F2 | Tool-layer security guards: SSRF on HTTP tool invocation, path-traversal/symlink escape checks, shell-metachar guards — unverified/missing in engine tools | S06 | **high** | M |
| F3 | Builders DAG runtime modules absent: `dag.py`(541L), `graph.py`(170L), `graph_executor.py`(285L), `pipeline.py`(554L) — the ADR-099/SPEC-201 gated verify-and-revise loop exists in stronghold code, engine has only the docs | S11 | missing | M–L |
| F4 | Orchestrator async queue-dispatcher pattern (WorkItem merge, dispatch API, polling coordination — 20 gaps) vs engine's wave-only orchestrator | S10 | missing | M–L |
| F5 | 4 missing DI protocol seams: `DataStore`, `RateLimiter`, `McpDeployerClient`, `VaultClient` | S13 | missing | S–M |
| F6 | `sessions/summarizer.py` episodic bridge absent from engine | S09 | missing | M |
| F7 | a2a delegation audit trail dropped `user_id` (tenant drop is by-design; user_id is not) | S15 | weaker | S |
| F8 | Type fixes: `GateResult.clarifying_questions` typed `tuple[Any,...]`; missing `ToolResult.sentinel_repaired` flag | S14 | weaker | S |
| F9 | SSE heartbeat pattern + LiteLLM dynamic model federation (portable patterns from chat/models routes) | S16 | partial | S–M |
| F10 | Engine `memory/learnings/embeddings` + hybrid lexical+vector retrieval scoring deltas; outcomes thumbs-down feedback loop | S07/S08 | partial | M |
| F11 | Stray auto-inserted `__import__()` logging in engine learnings promoter (lines ~163–170) — cleanup | S07 | cleanup | S |
| F12 | SSRF-mitigation docstring guidance dropped from 3 connector functions | S05 | doc | S |

## SKIP (Stronghold-owned per ADR-019/035, or superseded)

coin/wallet economy · hard tenant isolation · OIDC/Entra BFF · ADR-K8S infra series (001–012,16,17) ·
multi-tenant catalog ADRs (K8S-021/022/027) · server-rendered dashboards (React SPA supersedes) ·
DSPy library (ADR-039 rejected) · competitive/marketing comparison tables · most red-team infra
findings (engine Warden is ahead).

---

## Top-7 shortlist (if picking a minimal first PR)

1. A2UI adoption (A1) · 2. CapabilityProfile (A4) · 3. Six-tier priority (A6) ·
4. Light/heavy taxonomy (A5) · 5. Session Trust Floor (A7) · 6. COMPLIANCE.md (A2) ·
7. Warden L3 redirect + taxonomy (A10).
