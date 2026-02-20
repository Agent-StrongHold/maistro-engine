# Maistro Engine — Testing Infrastructure Audit

**Date:** 2026-02-20
**Scope:** Full codebase (`src/maistro/`, `tests/`, infrastructure configs)
**Methodology:** Six-agent parallel analysis covering property testing, contracts, chaos/fault injection, observability, mutation testing, and CI/CD pipeline infrastructure.

---

## 1. Executive Summary

Maistro Engine has a solid foundation of ~141 fast unit tests covering security pattern matching, API endpoint behavior, and task state machine logic, with an exemplary evidence-based docstring convention linking tests to real threat models. However, the testing infrastructure has critical gaps that would be unacceptable for a production multi-agent AI platform handling code execution in Docker sandboxes. There is no CI/CD pipeline — all quality gates are manual. Zero resilience tests exist for any of the 7 external dependencies (LiteLLM, Ollama, Docker, PostgreSQL, GitHub, Langfuse, Pydantic AI). The Docker sandbox construction — the most security-critical code path — has no test verifying that security flags like `--cap-drop=ALL` or `--network=none` are present. No property-based testing exists for the 14 adversarial-input security functions. No contract tests verify OpenAI-compatible API schema compliance, which Open WebUI depends on. The GitHub webhook signature verification function exists but is never called — webhooks are completely unauthenticated. 17 of 30 source files (57%) have zero test coverage, including the core conductor, task runner, queue, and Docker sandbox modules. Addressing these gaps requires three phases: quick wins (CI pipeline, coverage gates, pre-commit hooks, wiring up dead code — under 1 day each), medium investments (property tests, contract tests, integration tests, chaos tests — 1-2 weeks each), and strategic buildout (mutation testing, load testing, deployment automation — 1+ months).

---

## 2. Testing Health Scorecard

| Layer | Score | Justification |
|-------|-------|---------------|
| **Property Testing** | 0/10 | Zero Hypothesis tests exist; all 14 security-critical functions rely solely on hardcoded example inputs against effectively infinite adversarial input spaces. |
| **Evidence Grounding** | 5/10 | Tests reference real threat models (OpenClaw patterns, known injection payloads) via excellent evidence-based docstrings, but use static examples rather than production-observed data or fuzz-generated inputs. |
| **Contract Testing** | 2/10 | Pydantic models enforce some schema constraints and API tests check status codes and basic response shapes, but zero explicit contract tests exist for any of the 17 consumer-provider boundaries. |
| **Chaos / Resilience** | 0/10 | Zero fault injection tests across all 48 identified failure modes. No circuit breakers, no retry-with-backoff tests, no timeout enforcement tests, no degradation tests for any external dependency. |
| **Observability** | 1/10 | Structured logging exists for key lifecycle events and Langfuse tracing decorator is implemented, but the decorator is applied to zero functions, there are zero metrics, the health endpoint is shallow liveness-only, and zero behavioral assertions exist. |
| **Mutation Testing** | 0/10 | No mutation testing tooling installed. All 6 Docker sandbox security flags and the webhook signature verification have mutations that would survive undetected. 7 of the 10 highest-risk mutations survive. |
| **Infrastructure / Pipeline** | 1/10 | pytest, ruff, and mypy are installed and configured but enforced nowhere. No CI/CD pipeline, no pre-commit hooks, no coverage thresholds, no Makefile, no automated gates of any kind. |

---

## 3. Risk Register

Top 10 gaps ranked by **probability × blast radius** if they reach production.

| # | Risk | Prob. | Blast Radius | Source Agent | Affected Code |
|---|------|-------|-------------|-------------|---------------|
| 1 | **Docker sandbox security flags silently removed** — No test verifies `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory`, `--cpus`, `--network=none`, or `--pids-limit` in the Docker command. A refactoring that drops any flag passes all tests. | Medium | Critical — container escape, host compromise | Mutation (#5) | `src/maistro/tools/sandbox/docker.py:101-127` |
| 2 | **LiteLLM/Ollama total outage cascades to all tasks** — No circuit breaker; all concurrent tasks independently retry 3x with no backoff, creating thundering herd. No fast-fail after detecting outage. No per-request timeout ceiling. | High | Critical — total platform failure | Chaos (#3) | `src/maistro/agents/conductor.py:79-137` |
| 3 | **OpenAI-compatible API schema drift breaks Open WebUI** — No contract test verifies `/v1/chat/completions` response matches OpenAI schema (field names, types, nesting, `finish_reason` enum, `usage` fields). SSE streaming frame format (`data: {...}\n\n`, `data: [DONE]\n\n`) is completely untested. | Medium | Critical — entire UI breaks silently | Contract (#2) | `src/maistro/api/chat_completions.py` |
| 4 | **No CI/CD pipeline — all quality gates are manual** — A developer can push code that fails linting, type checking, and all tests with zero automated prevention. The entire test investment provides zero regression protection. | High | High — any quality regression ships | Pipeline (#6) | `.github/workflows/` (missing) |
| 5 | **Webhook signature verification is dead code** — `_verify_github_signature()` exists but is never called in the webhook handler. Any GitHub payload is accepted without authentication. An attacker can forge webhook events to create arbitrary tasks. | High | High — arbitrary task injection via forged webhooks | Mutation (#5), Chaos (#3) | `src/maistro/api/webhooks.py:19-24, 28-70` |
| 6 | **Docker `create_sandbox()` has no timeout** — If image pull stalls, worker blocks indefinitely. No watchdog to kill stuck subprocess. Multiple stalls exhaust all workers and halt the system. | Medium | Critical — worker exhaustion, system halt | Chaos (#3) | `src/maistro/tools/sandbox/docker.py:129-134` |
| 7 | **Zombie container accumulation** — No finally-block or context manager ensures containers are destroyed on exception. No periodic sweep, no reference tracking, no maximum container count. Containers accumulate until host resources are exhausted. | Medium | High — gradual host degradation then cascading failure | Chaos (#3) | `src/maistro/tools/sandbox/docker.py:72-80` |
| 8 | **Security validators vulnerable to Unicode bypass** — `detect_injection()`, `is_dangerous_command()`, `is_blocked_path()` tested with hardcoded examples only. Zero fuzz testing against Unicode homoglyphs, zero-width injections, encoding tricks, obfuscated command patterns. | Medium | High — security bypass | Property (#1) | `src/maistro/security/external_content.py`, `src/maistro/security/dangerous_tools.py` |
| 9 | **PostgreSQL is untested infrastructure** — Models defined in `memory/store.py`, connection configured, `tests/memory/` directory exists but is empty. Every failure mode (connection refused, pool exhaustion, query timeout, schema drift, missing pgvector extension) will be encountered for the first time in production. | High | High — data loss, startup failure, silent query errors | Chaos (#3), Pipeline (#6) | `src/maistro/memory/store.py`, `tests/memory/` (empty) |
| 10 | **No performance regression detection** — Zero tests assert timing, token consumption, or throughput. A change that makes the system 3x slower or 5x more expensive passes all tests identically. | High | Medium — invisible cost explosion and user experience degradation | Observability (#4) | Entire test suite |

---

## 4. Contract Coverage Matrix

Rows = consumers, columns = providers. Cells = coverage status.

| Consumer ↓ / Provider → | `/tasks` API | `/v1/chat/completions` | `/v1/models` | `/webhooks/github` | `/webhooks/ci` | `WS /stream` | MCP sandbox (6 tools) | MCP git (11 tools) | LiteLLM Proxy | Ollama | PostgreSQL | Docker Engine | GitHub API | Langfuse | Pydantic AI SDK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Custom Clients** | Partial | — | — | — | — | Missing | — | — | — | — | — | — | — | — | — |
| **Open WebUI** | — | **Partial** | **Partial** | — | — | — | — | — | — | — | — | — | — | — | — |
| **GitHub** | — | — | — | **Missing** | — | — | — | — | — | — | — | — | — | — | — |
| **CI Systems** | — | — | — | — | **Missing** | — | — | — | — | — | — | — | — | — | — |
| **Internal Agents** | — | — | — | — | — | — | **Missing** | **Missing** | — | — | — | — | — | — | — |
| **Maistro (outbound)** | — | — | — | — | — | — | — | — | **Missing** | **Missing** | **Missing** | **Missing** | **Missing** | **Missing** | **Missing** |

**Legend:** **Partial** = some happy-path status code tests, no schema snapshot or error-case contract | **Missing** = zero contract-level tests | **—** = no relationship

**Summary:** 4 boundaries have partial coverage. 13 boundaries have zero coverage. **0 boundaries have full contract coverage.**

### Priority Contracts to Implement

| Priority | Contract | Blast Radius | Effort |
|---|---|---|---|
| P0-1 | OpenAI `/v1/chat/completions` response schema + SSE frames | Critical — breaks Open WebUI | Medium |
| P0-2 | LiteLLM Proxy response contract (mock with schema validation) | Critical — breaks all LLM calls | Medium |
| P0-3 | OpenAI `/v1/models` response schema | High — breaks model discovery | Low |
| P1-1 | `POST /tasks` full contract (202 schema, 400/422 error shapes) | High — primary client API | Medium |
| P1-2 | GitHub webhook payload parsing + signature verification | High — missed webhooks, security | Medium |
| P1-3 | Docker Engine response contract (container create/exec/destroy) | High — sandbox is security-critical | High |
| P2-1 | PostgreSQL schema contract (ORM vs DB schema via Alembic) | High but slow-moving | Medium |
| P2-2 | MCP sandbox + git tool input/output schemas (17 tools) | High for agents | Medium |
| P2-3 | WebSocket `/stream/{task_id}` message frame contract | Medium-High | Medium |

---

## 5. Recommended Testing Architecture

### 5.1 Property Testing Layer

**Status:** Zero Hypothesis tests. 24 pure/deterministic functions identified, 20 suitable for property testing, 12 rated HIGH priority.

**Target:** Fuzz all adversarial-input security functions with [Hypothesis](https://hypothesis.readthedocs.io/). Structure as `tests/property/` directory.

| Priority | Function | Location | Key Invariant |
|---|---|---|---|
| 1 | `detect_injection(text)` | `security/external_content.py` | Known payloads always detected; benign text never flagged |
| 2 | `_normalize_text(text)` | `security/external_content.py` | Idempotent: `f(f(x)) == f(x)`; output never longer than input; ASCII preserved |
| 3 | `wrap_external_content` / `contains_markers` | `security/external_content.py` | Roundtrip: `contains_markers(wrap(x, ...)) == True` for all x |
| 4 | `sanitize_env(env)` | `tools/sandbox/env_sanitize.py` | Output ⊆ input; idempotent; no blocked keys; no secret values in output |
| 5 | `is_dangerous_command(cmd)` | `security/dangerous_tools.py` | Dangerous stems always detected regardless of obfuscation |
| 6 | `is_blocked_path(path)` | `security/dangerous_tools.py` | Blocked prefixes caught; path traversal variants caught |
| 7 | `validate_workspace_path(path)` | `tools/sandbox/workspace.py` | Traversal escape never succeeds; result always under allowed prefix |
| 8 | `looks_like_secret(value)` | `tools/sandbox/env_sanitize.py` | Known secret formats (AWS keys, JWTs, long hex) detected; normal values pass |
| 9 | `secret_equal(a, b)` | `security/secret_equal.py` | Reflexive, symmetric, consistent with `==` |
| 10 | `check_permission(grant, ...)` | `security/trust_boundary.py` | Expired grants always denied; matching non-expired grants always allowed |
| 11 | `_verify_github_signature(...)` | `api/webhooks.py` | HMAC sign-then-verify roundtrip always succeeds; wrong secret always fails |
| 12 | `secure_int(min, max)` | `security/secure_random.py` | Result always in `[min, max)` |

### 5.2 Contract Testing Layer

**Status:** Zero explicit contract tests. 4 partial boundaries, 13 completely missing.

**Target:** Schema snapshot tests for all API surfaces; recorded response fixtures for external dependencies.

**Recommended tools:** [Schemathesis](https://schemathesis.readthedocs.io/) for OpenAPI auto-testing, [respx](https://lundberg.github.io/respx/) for httpx request mocking with schema validation, [syrupy](https://github.com/toptal/syrupy) for snapshot assertions.

### 5.3 Chaos / Resilience Testing Layer

**Status:** Zero resilience tests across 48 identified failure modes. Zero circuit breakers. 5 of 22 external call sites have timeout protection.

**Target:** Verify graceful degradation for every external failure mode.

**Priority chaos scenarios (ranked by blast radius):**

| # | Scenario | Inject | Assert | Effort |
|---|---|---|---|---|
| 1 | LiteLLM total outage + concurrent load | Mock httpx → `ConnectError` for all requests; submit 20 tasks | All tasks fail within bounded time; no thundering herd; immediate recovery when mock removed | 2-3 hrs |
| 2 | Docker `create_sandbox()` hang | Mock subprocess → never returns; 60s test timeout | Sandbox creation times out within 30s; subprocess killed; worker released | 1-2 hrs |
| 3 | Docker fork bomb / resource exhaustion | Execute fork bomb inside sandbox | Container killed by cgroup limits; host stable; other containers unaffected | 2-3 hrs |
| 4 | Zombie container accumulation | Mock `destroy()` → raise exception after `create_sandbox()` succeeds; run 10 tasks | All containers cleaned up by periodic sweep or finally-block | 3-4 hrs |
| 5 | LiteLLM 429 rate limit | Mock httpx → 429 with `Retry-After: 2` for first 5 requests, then succeed | System respects Retry-After; exponential backoff applied; tasks eventually succeed | 2-3 hrs |
| 6 | Ollama OOM kill | Mock httpx → partial response (truncated JSON, connection reset) | Partial response detected; fallback or clean failure; subsequent tasks don't retry same model | 3-4 hrs |
| 7 | PostgreSQL pool exhaustion | Pool `max_size=2`; 2 long queries; submit 3rd | Clear "pool exhausted" error within timeout; no crash; recovery after long queries complete | 2-3 hrs |
| 8 | Langfuse mid-execution failure | Mock `trace.span()` → `ConnectionError` during agent execution | Agent execution succeeds despite tracing failure; error logged but not propagated | 1-2 hrs |

### 5.4 Observability Testing Layer

**Status:** Structured logging exists. Langfuse tracing decorator implemented but applied to zero functions. Zero metrics. Health endpoint is shallow liveness-only. Zero behavioral assertions.

**Target:**

| Test | Purpose |
|---|---|
| Conductor latency budget | Mock LLM at fixed latency, assert orchestration overhead < budget |
| Token consumption ceiling per tier | Assert tokens used < threshold per tier config |
| Concurrent task correctness | Submit N tasks, assert no cross-contamination of results |
| Sandbox cleanup on all exit paths | Assert Docker container count returns to baseline after all test paths |
| Deep health check | Assert health endpoint reports unhealthy when dependencies are down |
| Log output verification | Assert structured log entries emitted for key lifecycle events (task start, complete, fail) |

### 5.5 Mutation Testing Layer

**Status:** No mutation testing tooling. 7 of 10 highest-risk mutations survive.

**Critical mutation survivors — all Docker sandbox security flags:**

| Mutation | Survives? | Impact if Undetected |
|---|---|---|
| Remove `--cap-drop=ALL` | **YES** | Container gets full Linux capabilities |
| Remove `--security-opt=no-new-privileges` | **YES** | Processes can escalate privileges |
| Remove `--memory={limit}` | **YES** | Container can OOM-kill host |
| Remove `--cpus={count}` | **YES** | Container can starve host CPU |
| Remove `--network=none` conditional | **YES** | Network isolation never applied |
| Remove `--pids-limit` | **YES** | Fork bomb possible |
| Delete `_verify_github_signature()` | **YES** | No change — already dead code |
| Change `hmac.compare_digest` to `==` in auth | **YES** | Timing attack on API keys |

**Mutations caught by existing tests:** `is_dangerous_command()` inversion (parametrized tests), `secret_equal()` bypass (dedicated tests), `detect_injection()` skip (34 test functions), `sanitize_env()` filter removal (specific assertion tests), permission expiry flip (expiry test).

**Target:** [mutmut](https://mutmut.readthedocs.io/) targeting `src/maistro/security/` (90%+ kill rate) and `src/maistro/tools/sandbox/` (90%+ kill rate).

### 5.6 Infrastructure Layer

**Status:** No CI/CD. No pre-commit hooks. No Makefile. No coverage thresholds. pytest-cov installed but unconfigured.

**Current pipeline:**
```
Developer → (manual) pytest → (manual) ruff → (manual) mypy → git push → nothing happens
```

**Target pipeline:**
```
Pre-commit ──→ CI Stage 1 (< 3 min) ──→ CI Stage 2 (< 10 min) ──→ Build ──→ Deploy
     │              │                          │                       │          │
 ruff format    lint (ruff)              integration tests      Docker build   staging
 mypy           typecheck (mypy)         property tests         trivy scan     smoke tests
 detect-secrets unit tests + coverage    contract tests         registry push  promotion gate
               security scan (bandit,    mutation (non-blocking)
                pip-audit)
```

**Gap summary:**

| Stage | Exists? | Effort |
|---|---|---|
| CI/CD platform (GitHub Actions) | No | 2-4 hours |
| Pre-commit hooks | No | 1-2 hours |
| Lint gate (ruff in CI) | Tool installed, not gated | 30 min |
| Type check gate (mypy in CI) | Tool installed, not gated | 30 min |
| Unit test gate | Tool installed, not gated | 30 min |
| Coverage threshold | Tool installed, not configured | 30 min |
| Security scanning (bandit, pip-audit) | No | 1-2 hours |
| Integration tests (testcontainers) | No | 3-5 days |
| Property-based tests (Hypothesis) | No | 3-5 days |
| Contract tests (Schemathesis) | No | 2-3 days |
| Mutation testing (mutmut) | No | 1-2 days setup |
| Load testing (Locust) | No | 3-5 days |
| Container scanning (Trivy) | No | 2-3 hours |
| Deployment automation | No | 1-2 weeks |

---

## 6. Roadmap

### Phase 1: Quick Wins (< 1 day each)

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1.1 | **Create GitHub Actions CI workflow** — lint, typecheck, test+coverage, security scan as 4 parallel jobs | 2-4 hrs | Eliminates all manual gate enforcement; catches regressions immediately |
| 1.2 | **Add coverage configuration + threshold** — `[tool.coverage.run]` in pyproject.toml, `--cov-fail-under=40` (ratchet up over time) | 30 min | Prevents coverage regression |
| 1.3 | **Add pre-commit hooks** — ruff check+format, mypy, detect-secrets | 1-2 hrs | Catches issues before push |
| 1.4 | **Create Makefile** — `make lint`, `make test`, `make typecheck`, `make all` | 1 hr | Developer ergonomics |
| 1.5 | **Wire up `_verify_github_signature()`** — actually call it in the webhook handler; reject unauthenticated payloads | 1 hr | Closes the forged webhook vulnerability (Risk #5) |
| 1.6 | **Add Docker sandbox security flag test** — mock subprocess, assert `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory`, `--cpus`, `--network`, `--pids-limit` are all present | 2 hrs | Prevents silent removal of security flags (Risk #1) |
| 1.7 | **Apply `@trace_agent` decorator** to `run_task()` in conductor.py + fix Langfuse try/except scope | 30 min | Activates tracing for core code path; prevents observability from crashing business logic |

### Phase 2: Medium Investments (1-2 weeks each)

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 2.1 | **Property-based tests for security module** — Hypothesis for 12 HIGH-priority functions with strategies for adversarial Unicode, shell commands, path traversal, environment dicts | 3-5 days | Closes adversarial-input coverage gap for all security-critical code |
| 2.2 | **OpenAI-compatible API contract tests** — schema snapshot for `/v1/chat/completions` (non-streaming + SSE), `/v1/models`; verify all required fields, types, enum values | 2-3 days | Prevents silent breakage of Open WebUI integration (Risk #3) |
| 2.3 | **Integration test infrastructure** — `docker-compose.test.yml`, testcontainers for Postgres, session-scoped fixtures | 3-5 days | Enables database and service integration testing (Risk #9) |
| 2.4 | **Chaos test suite (scenarios 1-4)** — LiteLLM outage, Docker hang, fork bomb, zombie cleanup | 3-5 days | Proves resilience under the 4 highest-risk failure modes (Risk #2, #6, #7) |
| 2.5 | **LiteLLM + Ollama response contract mocks** — recorded fixtures with schema validation via respx | 2-3 days | Catches LiteLLM/Ollama version-bump breakage |
| 2.6 | **Webhook contract tests + conductor unit tests** — GitHub event parsing per event type; conductor with mocked LLM | 2-3 days | Covers the two largest untested code areas |

### Phase 3: Strategic Buildout (1+ months)

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 3.1 | **Mutation testing with mutmut** — target `security/` and `tools/sandbox/` at 90%+ kill rate; `agents/` at 80%+ | 1-2 weeks setup + ongoing | Proves test suite catches meaningful mutations, not just coverage |
| 3.2 | **Load / performance testing** — Locust baseline for task submission, chat completions, webhook processing, concurrent agents | 3-5 days | Establishes performance regression baselines (Risk #10) |
| 3.3 | **Full deployment pipeline** — staging environment, automated deploy, E2E smoke tests, rollback automation | 1-2 weeks | Production-readiness |
| 3.4 | **Observability-driven tests** — latency budgets per tier, token consumption ceilings, memory stability under load | 1 week | Catches performance and cost regressions |
| 3.5 | **Complete external dependency contract suite** — Docker Engine, PostgreSQL, Pydantic AI SDK, Langfuse, GitHub API, MCP tools | 2-3 weeks | Full contract coverage for all 13 missing boundaries |

---

## 7. Tooling Recommendations

| Layer | Tool | Why | Notes |
|-------|------|-----|-------|
| **Property Testing** | [Hypothesis](https://hypothesis.readthedocs.io/) `>=6.100` | Industry standard for Python property-based testing; native pytest integration | Configure `--hypothesis-seed` in CI for reproducibility. Use `@settings(max_examples=200)` in CI, 50 locally. |
| **Contract Testing** | [Schemathesis](https://schemathesis.readthedocs.io/) `>=3.30` | Auto-generates API tests from FastAPI's OpenAPI schema | Run against TestClient. Catches response schema drift automatically. |
| **HTTP Mocking** | [respx](https://lundberg.github.io/respx/) `>=0.21` | Mocks httpx requests (used by Pydantic AI / LiteLLM) with schema validation | Use for LiteLLM, Ollama, Langfuse response contract mocks. |
| **Snapshot Testing** | [syrupy](https://github.com/toptal/syrupy) `>=4.0` | Snapshot assertions for API response schemas | Use for contract snapshot tests on `/v1/chat/completions`, `/v1/models`. |
| **Mutation Testing** | [mutmut](https://mutmut.readthedocs.io/) `>=3.0` | Python-native mutation testing; simple config | Target `src/maistro/security/` first. Run as non-blocking CI job. |
| **Load Testing** | [Locust](https://locust.io/) `>=2.20` | Python-native, scriptable load testing | Scenarios for task submission, chat completions, concurrent agents. |
| **CI/CD** | GitHub Actions | Implied by GitHub webhook integration; free for open source | 4 parallel jobs: lint, typecheck, test+coverage, security. |
| **Security Scanning** | [pip-audit](https://pypi.org/project/pip-audit/) + [bandit](https://bandit.readthedocs.io/) | Dependency vulnerability audit + Python SAST | Run as CI job. |
| **Container Scanning** | [Trivy](https://aquasecurity.github.io/trivy/) | OS and application vulnerability scanning for Docker images | Run after Docker build in CI. |
| **Integration Tests** | [testcontainers-python](https://testcontainers-python.readthedocs.io/) `>=4.0` | Manages Docker containers for Postgres in tests | Session-scoped fixture with automatic schema migration. |
| **Pre-commit** | [pre-commit](https://pre-commit.com/) | Git hook manager | Plugins: ruff, mypy, detect-secrets, trailing-whitespace. |
| **Test Timeout** | pytest-timeout `>=2.3` | Prevents hung tests | Add `timeout = 30` to `[tool.pytest.ini_options]`. |

---

## Appendix A: Failure Mode Inventory

### A.1 LiteLLM Proxy (HTTP via Pydantic AI / httpx)

| Failure Mode | Current Handling | Tested? | Blast Radius |
|---|---|---|---|
| Connection refused (service down) | Pydantic AI retries 3x → TaskStatus.FAILED | No | Critical |
| DNS resolution failure | Same as connection refused | No | Critical |
| TCP timeout (service hangs) | httpx default timeout, 3 retries consume 3× timeout | No | High |
| HTTP 429 (rate limit) | No backoff, no Retry-After respect | No | Critical |
| HTTP 500/502/503 | Retries 3x without backoff → thundering herd | No | High |
| HTTP 401/403 (auth failure) | Wastes retry budget on non-retryable error | No | Medium |
| Malformed JSON response | Parse error → retries → fails | No | Medium |
| Partial/truncated response | No partial response recovery or validation | No | High |
| Extremely slow response (>10 min) | No per-request ceiling timeout | No | High |
| Context window exceeded | No pre-flight check; error or truncation | No | Medium |

### A.2 Docker Engine (subprocess)

| Failure Mode | Current Handling | Tested? | Blast Radius |
|---|---|---|---|
| Daemon not running | RuntimeError raised | No | Critical |
| Image pull stalls (`docker run` hangs) | **No timeout on create_sandbox()** | No | Critical |
| Container OOM kill during exec | Generic Exception caught, opaque "Killed" message | No | Medium |
| Container exits between create and exec | Generic Exception caught | No | Medium |
| Disk full | docker run fails, RuntimeError | No | High |
| `docker rm -f` fails during destroy | Unclear if caught; orphaned reference | No | Low |
| Zombie containers (exception before cleanup) | No finally block or context manager | No | High |
| Fork bomb / resource exhaustion | `--pids-limit` set but untested | No | Critical |

### A.3 PostgreSQL (asyncpg / SQLAlchemy)

| Failure Mode | Current Handling | Tested? | Blast Radius |
|---|---|---|---|
| Connection refused | Unhandled crash | No | Critical |
| Pool exhaustion | Blocks then timeout, no backpressure | No | Critical |
| Query timeout | No statement_timeout configured | No | High |
| Connection drop mid-transaction | No retry with reconnect | No | High |
| Auth failure (credential rotation) | Startup failure | No | Critical |
| pgvector extension missing | Cryptic "type does not exist" error | No | High |
| Deadlock | No retry logic | No | Medium |

### A.4 Langfuse (HTTP)

| Failure Mode | Current Handling | Tested? | Blast Radius |
|---|---|---|---|
| Service unavailable at init | `get_langfuse()` catches Exception → None → tracing skipped | No | Low |
| `trace.span()` raises mid-execution | **NOT caught** — observability crash kills business logic | No | Medium |
| `langfuse.flush()` hangs or blocks | No timeout on flush | No | Medium |

### A.5 GitHub API (gh CLI subprocess)

| Failure Mode | Current Handling | Tested? | Blast Radius |
|---|---|---|---|
| gh CLI not installed | Unhandled `FileNotFoundError` | No | Medium |
| API rate limit (403) | `get_pr()` returns error dict; `list_issues()` returns `[]` silently | No | Medium |
| Network timeout (30s) | Timeout exists, no retry | No | Low |
| Malformed JSON from gh | json.loads exception propagates | No | Low |
| `list_issues()` returns `[]` on failure | **Silent data loss** — caller cannot distinguish "no issues" from "API failed" | No | Medium |

---

## Appendix B: Mutation Survival Analysis (Full)

### B.1 Docker Sandbox Security (CRITICAL — All Mutations Survive)

| Mutation | Survives? | Impact |
|---|---|---|
| Remove `--cap-drop=ALL` | **YES** — no test checks Docker command | Container gets full Linux capabilities |
| Remove `--security-opt=no-new-privileges` | **YES** | Container processes can escalate privileges |
| Remove `--memory={limit}` | **YES** | Container can OOM-kill host |
| Remove `--cpus={count}` | **YES** | Container can starve host CPU |
| Remove `--network=none` conditional | **YES** | Network isolation never applied |
| Remove `--pids-limit` | **YES** | Fork bomb possible |
| Add `--privileged` flag | **YES** — no negative test | Full host access from container |

### B.2 Webhook Signature

| Mutation | Survives? | Impact |
|---|---|---|
| Delete `_verify_github_signature()` entirely | **YES** — never called | No change (already dead code) |
| Return `True` unconditionally | **YES** — never tested | No change (already unused) |
| Change `hmac.compare_digest` to `==` | **YES** — no test calls function | Timing attack possible |

### B.3 Auth Logic

| Mutation | Survives? | Impact |
|---|---|---|
| Flip `if not settings.api_keys` condition | **NO** — caught by `test_no_keys_allows_all` | Auth required when no keys configured |
| Change status 401 to 400 | **NO** — tests assert status code | Wrong error code |
| Change `hmac.compare_digest` to `==` | **YES** — timing safety untested | Timing attack on API keys |
| Remove key iteration, return unconditionally | **NO** — caught by `test_wrong_key_rejected` | Any key accepted |

### B.4 Permission Expiry

| Mutation | Survives? | Impact |
|---|---|---|
| Flip `>` to `<` in expiry check | **NO** — caught by `test_expired_grant` | Expired accepted, valid denied |
| Delete expiry check entirely | **NO** — caught by `test_expired_grant` | Grants never expire |
| Change `Action.EXECUTE` to `Action.READ` | **NO** — caught by `test_execute_permission` | Execute treated as read |

### B.5 Env Sanitization

| Mutation | Survives? | Impact |
|---|---|---|
| Remove `not is_blocked_name(k)` check | **NO** — caught by existing tests | Blocked env vars leak |
| Remove `not looks_like_secret(v)` check | **NO** — caught by existing tests | Secret values leak |
| Flip `and` to `or` in filter | **NO** — caught by existing tests | Either blocked names or secrets leak |

### B.6 Weak Assertion Patterns

The test suite uses `assert len(matches) > 0` in 23 injection detection tests (e.g., `test_ignore_previous_instructions`, `test_rm_rf`, `test_sql_injection`). This assertion passes for **any** non-empty list regardless of which pattern matched or whether the detection is correct. Mutations that change which pattern matches — or return a garbage list — survive these assertions.

**Recommendation:** Strengthen to `assert any("expected_pattern" in m for m in matches)` or assert the specific matched pattern name.

---

## Appendix C: Observability Inventory

### Instrumentation Present

| Type | Count | Details |
|---|---|---|
| Logger instances | 8 | structlog-based, JSON output |
| Log emission points | 13 | Task lifecycle, errors, startup |
| Langfuse tracing decorator | 1 | `trace_agent()` — **applied to 0 functions** |
| Health endpoints | 1 | `GET /health` — shallow liveness only |
| Prometheus/metrics | 0 | None |
| Performance assertions | 0 | None |
| SLA/latency tests | 0 | None |

### Critical Observability Gaps

1. **`@trace_agent` decorator is dead code** — defined in `observability/tracing.py` but imported and used nowhere
2. **No readiness probe** — health check returns `{"status": "ok"}` unconditionally; doesn't check DB, LLM, Docker
3. **No metrics** — no request rates, latencies, error rates, queue depth, token usage, sandbox counts
4. **No behavioral assertions** — test suite cannot detect latency regressions, memory leaks, throughput degradation
5. **Langfuse `trace.span()` outside try/except** — tracing failure crashes business logic (observer effect antipattern)
6. **`_extract_usage()` always returns 0** — token/cost tracking has wrong response format assumption

---

## Appendix D: Property-Based Testing Candidates (Full)

| # | Function | Location | Input Complexity | Priority |
|---|---|---|---|---|
| 1 | `detect_injection(text)` | `security/external_content.py` | HIGH — arbitrary UTF-8, Unicode confusables | **HIGH** |
| 2 | `_normalize_text(text)` | `security/external_content.py` | HIGH — full Unicode range, NFKC edge cases | **HIGH** |
| 3 | `contains_markers(text)` | `security/external_content.py` | MEDIUM — Unicode normalization | **HIGH** |
| 4 | `wrap_external_content(...)` | `security/external_content.py` | MEDIUM — arbitrary content + metadata | **HIGH** |
| 5 | `is_dangerous_command(cmd)` | `security/dangerous_tools.py` | HIGH — shell strings, quoting, pipes | **HIGH** |
| 6 | `is_blocked_path(path)` | `security/dangerous_tools.py` | MEDIUM — path normalization, traversal | **HIGH** |
| 7 | `sanitize_env(env)` | `tools/sandbox/env_sanitize.py` | HIGH — arbitrary dict[str,str] | **HIGH** |
| 8 | `looks_like_secret(value)` | `tools/sandbox/env_sanitize.py` | HIGH — secret vs normal value boundary | **HIGH** |
| 9 | `validate_workspace_path(path)` | `tools/sandbox/workspace.py` | MEDIUM — traversal attempts | **HIGH** |
| 10 | `check_permission(...)` | `security/trust_boundary.py` | MEDIUM — glob patterns, expiry, actions | **HIGH** |
| 11 | `secret_equal(a, b)` | `security/secret_equal.py` | LOW — two strings | **HIGH** |
| 12 | `_verify_github_signature(...)` | `api/webhooks.py` | MEDIUM — bytes payload + HMAC | **HIGH** |
| 13 | `is_blocked_name(name)` | `tools/sandbox/env_sanitize.py` | MEDIUM — prefix matching | MEDIUM |
| 14 | `TaskSpec.validate_spec()` | `security/trust_boundary.py` | MEDIUM — structured object | MEDIUM |
| 15 | `_matches_glob(path, patterns)` | `security/trust_boundary.py` | MEDIUM — fnmatch semantics | MEDIUM |
| 16 | `can_transition(current, target)` | `tasks/status.py` | LOW — finite enum × enum | MEDIUM |
| 17 | `secure_id(n_bytes)` | `security/secure_random.py` | LOW — integer input | MEDIUM |
| 18 | `secure_int(min, max)` | `security/secure_random.py` | LOW — integer range | MEDIUM |
| 19 | `secure_base36(length)` | `security/secure_random.py` | LOW — integer input | MEDIUM |
| 20 | `secure_urlsafe(n_bytes)` | `security/secure_random.py` | LOW — integer input | MEDIUM |
| 21 | `is_dangerous_tool(name)` | `security/dangerous_tools.py` | LOW — frozenset lookup | LOW |
| 22 | `create_grant_for_task(...)` | `security/trust_boundary.py` | LOW — factory function | LOW |
| 23 | `verify_api_key(...)` | `api/auth.py` | LOW — bearer token | LOW |
| 24 | `_get_tier_config(tier)` | `agents/conductor.py` | LOW — Tier enum (4 values) | LOW |

---

## Appendix E: Source File Coverage Map

```
src/maistro/
├── agents/
│   ├── conductor.py      (137 lines, 0% tested)  ← CRITICAL gap
│   ├── prompts.py         (57 lines, 0% tested)
│   └── types.py           (58 lines, tested)       ✓
├── api/
│   ├── auth.py            (49 lines, tested)       ✓
│   ├── chat_completions.py (163 lines, 0% tested) ← HIGH gap
│   ├── health.py          (23 lines, tested)       ✓
│   ├── models.py          (40 lines, tested)       ✓
│   ├── tasks.py           (68 lines, tested)       ✓
│   ├── webhooks.py        (94 lines, partial)      ⚠ signature dead code
│   └── ws.py              (63 lines, 0% tested)
├── config/
│   ├── models.py          (60 lines, 0% tested)
│   └── settings.py        (80 lines, 0% tested)
├── memory/
│   └── store.py           (79 lines, 0% tested)   ← HIGH gap
├── observability/
│   └── tracing.py         (62 lines, 0% tested)    dead decorator
├── security/
│   ├── dangerous_tools.py (89 lines, tested)       ✓
│   ├── external_content.py (125 lines, tested)     ✓
│   ├── secret_equal.py    (33 lines, tested)       ✓
│   ├── secure_random.py   (35 lines, tested)       ✓
│   └── trust_boundary.py  (121 lines, tested)      ✓
├── tasks/
│   ├── models.py          (66 lines, partial)
│   ├── queue.py          (109 lines, 0% tested)   ← HIGH gap
│   ├── runner.py         (104 lines, 0% tested)   ← HIGH gap
│   └── status.py          (43 lines, tested)       ✓
├── tools/
│   ├── git/
│   │   ├── github.py      (67 lines, 0% tested)
│   │   └── server.py     (169 lines, 0% tested)
│   └── sandbox/
│       ├── docker.py     (146 lines, 0% tested)   ← CRITICAL gap
│       ├── env_sanitize.py (85 lines, tested)      ✓
│       ├── server.py     (110 lines, 0% tested)
│       └── workspace.py   (43 lines, tested)       ✓
└── main.py                (62 lines, 0% tested)

Tested: 13 files (~910 lines)
Untested: 17 files (~1,468 lines, 62%)
```
