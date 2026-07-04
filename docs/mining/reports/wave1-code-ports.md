# Wave-1 report: code-port manifest + API-layer regressions (condensed digest)

## Port manifest (mcp / cache / resources / sandbox) — all absent from engine (grep-verified)
Generalization rule everywhere: `tenant_id` → soft scope axes / `org_id` (ADR-068); rename
`stronghold://` scheme + `stronghold:` key prefixes; K8s concretions stay behind protocols.

| Item | Source | Target | Effort |
|---|---|---|---|
| RedisSessionStore (TTL, poison-tolerant parse, SEC-009 filters) | cache/session_store.py:22 | sessions/redis_store.py | S–M |
| RedisRateLimiter (sliding-window ZSET, same header contract as InMemory) | cache/rate_limiter.py:21 | security/rate_limiter.py | S |
| RedisPromptCache + redis_pool (get_redis singleton, _mask_url) | cache/{prompt_cache,redis_pool}.py | cache/ | S |
| ResourceCatalog (URI templates, per-call credential injection, scope isolation) | resources/catalog.py | resources/ | M |
| MCP types + MCPRegistry + KNOWN_MCP_SERVERS + image allow-list (C12) | mcp/{types,registry}.py | mcp/ | M |
| External registry aggregation (Smithery/official/Glama, scan_registry_server heuristics + warden hook) | mcp/registries.py | mcp/registries.py | M |
| MCP OAuth 2.1 server (RFC 8414/7591/7009, PKCE S256, argon2 store→core; FastAPI endpoints→maistro-server) | mcp/oauth/* | mcp/oauth/ | M |
| SandboxBudgetEnforcer (per-scope pod/CPU/mem ceilings) | sandbox/budgets.py | sandbox/budgets.py | S–M |
| SecurityProfile + 6 hardened templates (SHELL/PYTHON/BROWSER/FILESYSTEM/K8S/NETWORK; seccomp, drop-caps) | sandbox/catalog.py:37-178 | sandbox/pod_catalog.py | M |
| FakeMCPDeployerClient (test fake) | sandbox/deployer.py:109 | testing/ | S |
| SKIP: K8sDeployer, sidecar MCPDeployerClient, sandbox/templates.py (superseded) | — | Stronghold | — |

New deps: runtime `redis[hiredis]`; test `fakeredis`, `respx`. `httpx`+`argon2-cffi` already present.
Tests to port: tests/cache/* (289 LOC), tests/resources/ (151), tests/mcp/test_registries_coverage.py
(625), tests/mcp/test_oauth.py (361+114), tests/sandbox/ (737).

## API-layer regressions (working+tested in stronghold, missing/weaker in engine)
Product-agnostic subset only (multi-tenant/OIDC/coins = Stronghold-owned, skip):

1. **Global payload-size 413 middleware** (api/middleware/__init__.py:16; tested 7 cases) —
   engine has per-route webhook check only; no `max_request_body_bytes` setting. S–M.
2. **Cross-model LLM fallback** (api/litellm_client.py:27; 15+ tests) — phase-1 explicit chain,
   phase-2 `/v1/models` discovery + dedupe; retryable {400-cooldown,422,429,5xx} vs raise
   401/403. Engine: same-model retry + circuit breaker only; `providers/router.fallback_chain`
   not wired into HTTP call path. M–L.
3. **Security-headers middleware** (security_headers.py:24) — HSTS, XFO DENY, nosniff,
   Referrer-Policy, Permissions-Policy. Absent everywhere in engine. S.
4. **Per-user rate limiting** (rate_limit.py:44) — identity keying (user-header → auth-hash →
   IP), login/register NOT exempt (brute-force), X-RateLimit-* headers. Engine: per-IP bucket,
   /health-only exempt. M.
5. **CSRF custom-header check** on state-changing POSTs (auth.py:43; tested) — absent. S.
6. **Session ownership + `_validate_session_id` path-traversal regex** (sessions.py:19-115;
   tested) — hive chat sessions have no ownership check, no ID validation (org-scope axis =
   in-scope for engine). M.
7. **Demo-cookie → Authorization ASGI injection** (demo_cookie.py:20; tested) —
   DemoCookieAuthProvider survives in core but nothing at HTTP layer feeds it. M.
8. Prometheus text `/metrics` (KEDA-scrapable) + `/status/reactor` — engine metrics are
   JSON-only. S–M.
9. Learnings moderation HTTP surface (list/add-with-Warden-scan/approve/reject) — approval gate
   exists in core, not exposed. M.
10. Enriched quota analytics (burn rate, days-to-exhaustion, usage breakdown, timeseries) —
    engine quotas.py returns zeroed fallbacks. L (needs usage store).

Non-regressions confirmed: agent strategies (parity, clean port); engine exception envelopes +
request-ID middleware are net improvements; hive `/auth/elevate` is new capability.
