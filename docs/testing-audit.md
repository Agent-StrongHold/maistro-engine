# Maistro Engine -- Testing Infrastructure Audit

**Date**: 2026-02-20
**Scope**: Full-spectrum analysis of testing infrastructure, coverage, resilience, contracts, observability, mutation survivability, and CI/CD pipeline.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Overview](#2-current-state-overview)
3. [Coverage Analysis](#3-coverage-analysis)
4. [Property-Based Testing Gaps](#4-property-based-testing-gaps)
5. [Contract & Boundary Testing Gaps](#5-contract--boundary-testing-gaps)
6. [Chaos & Fault Injection Analysis](#6-chaos--fault-injection-analysis)
7. [Observability & Behavioral Testing Gaps](#7-observability--behavioral-testing-gaps)
8. [Mutation Survivability Analysis](#8-mutation-survivability-analysis)
9. [Infrastructure & Pipeline Gaps](#9-infrastructure--pipeline-gaps)
10. [Unified Risk Matrix](#10-unified-risk-matrix)
11. [Prioritized Remediation Roadmap](#11-prioritized-remediation-roadmap)

---

## 1. Executive Summary

The Maistro Engine has a **well-structured but incomplete** testing foundation. The security test suite is remarkably thorough, the tooling choices (pytest, ruff, mypy strict) are sound, and the evidence-based docstring convention is exemplary. However, critical gaps exist across every analysis dimension:

| Metric | Value |
|---|---|
| Total test functions | ~141 |
| Estimated line coverage | ~38% |
| Source lines with zero test coverage | ~1,468 of ~2,378 (62%) |
| Untested async code paths | 100% (all async code is untested) |
| External call sites | 22 |
| Identified failure modes | 48 |
| Failure modes with test coverage | **0 (0%)** |
| Mutation survivors (critical) | 7 of 10 highest-risk mutations |
| Property-based tests | 0 |
| Contract tests | 0 |
| CI/CD pipelines | 0 |
| Resilience mechanisms (retry/circuit breaker) | 1 partial (PydanticAI output validation only) |

**The three most dangerous findings:**

1. **The LLM provider call (`conductor.py:135`) has no timeout, no retry, and no circuit breaker.** A single slow or failed LLM request blocks all task processing because the task runner is single-threaded. This is a service-level outage waiting to happen.

2. **The GitHub webhook signature verification (`webhooks.py:19-24`) is dead code -- never called.** Webhooks are completely unauthenticated. Any attacker can forge webhook events to create arbitrary tasks.

3. **There is no CI/CD pipeline.** Tests, linting, and type checking are never enforced. The existing test investment provides zero protection against regressions because nothing runs automatically.

---

## 2. Current State Overview

### 2.1 Test Tooling

| Tool | Version | Purpose | Status |
|---|---|---|---|
| pytest | `>=8.3` | Test runner | Configured, working |
| pytest-asyncio | `>=0.25` | Async test support | Configured (`asyncio_mode = "auto"`), but no async tests exist |
| pytest-cov | `>=6.0` | Coverage measurement | Installed but **unconfigured** (no thresholds, no report config) |
| ruff | `>=0.9` | Linter + formatter | Configured with good rule selection |
| mypy | `>=1.14` | Type checker | Configured in strict mode with Pydantic plugin |

**Notable absences**: pytest-xdist, pytest-timeout, pytest-randomly, hypothesis, factory-boy, pytest-mock, bandit, pre-commit.

### 2.2 Test Suite Composition

| Directory | Tests | Focus |
|---|---|---|
| `tests/agents/` | 5 | Pydantic model validation for agent types |
| `tests/api/` | 30 | REST endpoint CRUD, auth, health, webhooks, status |
| `tests/security/` | 92 | Injection detection, dangerous tools, trust boundaries, secrets |
| `tests/tools/` | 14 | Env sanitization, workspace path validation |
| `tests/memory/` | 0 | Empty `__init__.py` only |
| **Total** | **~141** | |

### 2.3 Test Patterns

| Pattern | Used | Notes |
|---|---|---|
| Class-based grouping (`class Test*`) | Yes | All test files |
| `pytest.raises` | Yes | Exception testing |
| `@pytest.mark.parametrize` | Yes | Security and tools tests |
| FastAPI `TestClient` | Yes | API tests |
| Evidence-based docstrings | Yes | Every test file (excellent practice) |
| Async tests (`async def test_*`) | **No** | Zero async tests despite async codebase |
| Mocking (`unittest.mock`) | **No** | Zero use of mocking anywhere |
| Property-based testing | **No** | Zero use of hypothesis |
| Integration tests | **No** | No database, no Docker, no real I/O |

### 2.4 Python Version Inconsistency

| Location | Version |
|---|---|
| `.python-version` | 3.13 |
| `pyproject.toml` requires-python | `>=3.12` |
| `Dockerfile` | `python:3.12-slim` |
| `mypy` python_version | 3.12 |
| Runtime environment | Python 3.11 (incompatible with `>=3.12`) |

---

## 3. Coverage Analysis

### 3.1 Modules WITH Tests

| Source Module | Test File | Quality |
|---|---|---|
| `agents/types.py` (58 lines) | `tests/agents/test_types.py` | Good |
| `api/auth.py` (49 lines) | `tests/api/test_auth.py` | Good |
| `api/health.py` (23 lines) | `tests/api/test_health.py` | Good |
| `api/tasks.py` (68 lines) | `tests/api/test_tasks.py` | Good |
| `api/webhooks.py` (94 lines) | `tests/api/test_webhooks.py` | Partial (`_verify_github_signature` untested) |
| `api/models.py` (40 lines) | `tests/api/test_tasks.py` | Good |
| `tasks/status.py` (43 lines) | `tests/api/test_status.py` | Excellent |
| `tasks/models.py` (66 lines) | Indirect via test_tasks | Partial |
| `security/dangerous_tools.py` (89 lines) | `tests/security/test_dangerous_tools.py` | Excellent |
| `security/external_content.py` (125 lines) | `tests/security/test_external_content.py` | Excellent |
| `security/secret_equal.py` (33 lines) | `tests/security/test_secret_equal.py` | Excellent |
| `security/secure_random.py` (35 lines) | `tests/security/test_secure_random.py` | Good |
| `security/trust_boundary.py` (121 lines) | `tests/security/test_trust_boundary.py` | Good |
| `tools/sandbox/env_sanitize.py` (85 lines) | `tests/tools/test_env_sanitize.py` | Good |
| `tools/sandbox/workspace.py` (43 lines) | `tests/tools/test_workspace.py` | Good |

### 3.2 Modules WITHOUT Tests (0% Coverage)

| Source Module | Lines | Risk |
|---|---|---|
| `agents/conductor.py` | 137 | **CRITICAL** -- core orchestration, LLM integration |
| `api/chat_completions.py` | 163 | **HIGH** -- streaming SSE, OpenAI compat |
| `api/ws.py` | 63 | Medium -- WebSocket streaming |
| `config/settings.py` | 80 | Medium -- env loading |
| `config/models.py` | 60 | Low -- tier definitions |
| `main.py` | 62 | **HIGH** -- lifespan, startup/shutdown |
| `memory/store.py` | 79 | Medium -- SQLAlchemy models |
| `observability/tracing.py` | 62 | Medium -- Langfuse integration |
| `tasks/queue.py` | 109 | **HIGH** -- async queue, state management |
| `tasks/runner.py` | 104 | **HIGH** -- background worker |
| `tools/sandbox/docker.py` | 146 | **HIGH** -- Docker container management |
| `tools/sandbox/server.py` | 110 | Medium -- MCP tool server |
| `tools/git/github.py` | 67 | Medium -- gh CLI wrapper |
| `tools/git/server.py` | 169 | Medium -- MCP git tools |
| `agents/prompts.py` | 57 | Low -- static strings |
| **Total untested** | **~1,468** | |

### 3.3 Coverage Configuration Gap

pytest-cov is installed but completely unconfigured. No `[tool.coverage.run]` section, no `--cov-fail-under`, no `.coveragerc`. The `.gitignore` references coverage artifacts, indicating it has been run manually at least once.

---

## 4. Property-Based Testing Gaps

### 4.1 Functions Suitable for Property-Based Testing

21 pure functions were identified as candidates. The highest-priority targets:

| Priority | Function | File:Line | Property to Test |
|---|---|---|---|
| **P0** | `detect_injection(text)` | `security/external_content.py:20` | For all strings, if detect returns True the string must contain a pattern from the known-bad set; for all safe strings, must return False |
| **P0** | `is_dangerous_command(cmd)` | `security/dangerous_tools.py:34` | Arbitrary shell strings: no false negatives for `rm -rf /`, `:(){ :\|: & };:`, etc. |
| **P0** | `sanitize_env(env)` | `tools/sandbox/env_sanitize.py:30` | For any dict input, output never contains keys matching secret patterns; output is always a subset of input |
| **P0** | `secret_equal(a, b)` | `security/secret_equal.py:9` | Equivalence with `==` for all string pairs; constant-time property |
| **P1** | `is_safe_url(url)` | `security/external_content.py:61` | No private IPs (10.x, 172.16-31.x, 192.168.x, 127.x) ever return True |
| **P1** | `is_blocked_path(path)` | `tools/sandbox/workspace.py:25` | Blocked prefixes remain blocked under path normalization (`/../`, `//`, `./`) |
| **P1** | `validate_model_access(model, tier)` | `config/models.py:42` | Tier ordering is respected (higher tier grants superset of lower tier access) |
| **P2** | `sanitize_content(text)` | `security/external_content.py:87` | Output length <= input length; no injection patterns survive |
| **P2** | `secure_random_token(n)` | `security/secure_random.py:12` | Length is always `n`; character set is correct; distribution is uniform |

### 4.2 Potential Security Bug Found

`is_blocked_path()` in `tools/sandbox/workspace.py:25` does **not normalize paths** before checking prefixes. An attacker could bypass path blocking with:
- `/tmp/../etc/passwd` -- the prefix `/tmp/` matches the allowed list, but the resolved path is `/etc/passwd`
- `//etc/passwd` -- double-slash normalization
- `/tmp/./../../etc/shadow` -- dot-segment traversal

**Recommendation**: Add `os.path.realpath()` or `pathlib.Path.resolve()` before prefix checking, and add property-based tests using hypothesis to generate adversarial paths.

### 4.3 Evidence Anchor Gaps

The test suite uses an "Evidence:" docstring convention linking tests to threat models. 9 existing anchors reference real security frameworks (OWASP, CWE). 7 source modules with security implications have **no corresponding evidence anchors**:

| Module | Missing Evidence |
|---|---|
| `agents/conductor.py` | No prompt injection evidence |
| `api/chat_completions.py` | No streaming security evidence |
| `api/ws.py` | No WebSocket auth evidence |
| `tools/sandbox/docker.py` | No container escape evidence |
| `tools/git/server.py` | No command injection evidence |
| `tasks/queue.py` | No denial-of-service evidence |
| `observability/tracing.py` | No data exfiltration evidence |

---

## 5. Contract & Boundary Testing Gaps

### 5.1 Service Boundary Inventory

22 distinct service boundaries were identified:

| Category | Count | Boundaries |
|---|---|---|
| REST API endpoints | 10 | `/health`, `/tasks` CRUD, `/v1/chat/completions`, `/webhooks/*`, `/v1/models` |
| WebSocket endpoints | 1 | `/stream/{task_id}` |
| MCP Tool interfaces | 16 | 8 sandbox tools, 8 git tools |
| External dependencies | 6 | LLM providers, PostgreSQL, Langfuse, Docker, GitHub API, Git CLI |

### 5.2 Contract Test Coverage: Zero

There are **zero formal contract tests** in the codebase. Key gaps:

| Priority | Contract | Gap |
|---|---|---|
| **P0** | OpenAI `/v1/chat/completions` streaming SSE format | No test verifies `data: [DONE]` termination, chunk format, or `choices[0].delta` structure |
| **P0** | OpenAI `/v1/chat/completions` non-streaming response | No test verifies `id`, `object`, `created`, `model`, `choices`, `usage` fields match OpenAI spec |
| **P0** | OpenAI `/v1/models` response format | No test verifies model list matches OpenAI's `ListModelsResponse` schema |
| **P1** | LLM provider request contract (PydanticAI -> Ollama/LiteLLM) | No test verifies request format, auth headers, model name mapping |
| **P1** | MCP tool input/output schemas | 16 MCP tools have no schema validation tests |
| **P1** | Task state machine transitions | Status transitions are tested (`test_status.py`) but not as a formal state machine contract |
| **P2** | GitHub webhook payload contract | No test validates expected fields from GitHub webhook events |
| **P2** | Docker CLI argument contract | No test verifies Docker commands use correct flags and argument ordering |
| **P2** | Langfuse trace/span contract | No test verifies trace data format matches Langfuse expectations |

### 5.3 Pydantic Schema Drift Risk

The codebase uses Pydantic models extensively (18 models across 6 files). Schema changes have no contract tests to catch breaking changes at service boundaries. The `TaskCreate`, `TaskResponse`, and `ChatCompletionRequest` models are public API surfaces with zero schema regression tests.

---

## 6. Chaos & Fault Injection Analysis

### 6.1 External Call Sites & Resilience

| Category | Call Sites | Timeout Protected | Retry Protected | Circuit Breaker |
|---|---|---|---|---|
| LLM Provider (HTTP) | 5 | **0 of 5** | 0 (PydanticAI retries are for validation only) | 0 |
| Langfuse (HTTP) | 5 | 0 | 0 | 0 |
| Docker subprocess | 3 | 2 of 3 (`exec` has timeout; `run` does not) | 0 | 0 |
| Git subprocess | 3 | 2 of 3 (`_git` has timeout; `git_clone` does not) | 0 | 0 |
| GitHub CLI subprocess | 2 | 1 of 2 | 0 | 0 |
| WebSocket | 4 | 0 | 0 | 0 |
| **Total** | **22** | **5 of 22 (23%)** | **0** | **0** |

### 6.2 Top Failure Modes (by blast radius)

**CRITICAL -- Service-Level Outage:**

| # | Failure Mode | Impact | Location |
|---|---|---|---|
| 1 | **LLM provider unavailable (no timeout, no retry)** | ALL users blocked. `agent.run()` hangs indefinitely. Single-worker runner stalls entire queue. | `conductor.py:135`, `runner.py:74` |
| 2 | **Process restart loses all task state** | ALL active tasks lost. In-memory queue has no persistence despite SQLAlchemy models existing. | `queue.py:26-27` |
| 3 | **Background task runner has no execution timeout** | One hung LLM call blocks all subsequent tasks forever. | `runner.py:74` |
| 4 | **No rate limiting on any API endpoint** | Service DoS via queue flooding or LLM resource exhaustion. | All API routers |

**HIGH -- Feature-Level Failure:**

| # | Failure Mode | Impact | Location |
|---|---|---|---|
| 5 | **Docker daemon failure** | All sandbox operations fail. No retry, no fallback. | `docker.py:129-138` |
| 6 | **Git clone has no timeout** | `await proc.communicate()` hangs indefinitely on slow/large repos. | `server.py:38-43` |
| 7 | **Webhook signature verification is dead code** | Webhooks completely unauthenticated. Attacker can create arbitrary tasks. | `webhooks.py:19-24` |
| 8 | **Langfuse trace/span calls crash agent execution** | `langfuse.trace()` at line 47 is outside try/except. Langfuse outage crashes LLM calls. Observability becomes a single point of failure. | `tracing.py:47-48` |

**MEDIUM -- Degraded Experience:**

| # | Failure Mode | Impact | Location |
|---|---|---|---|
| 9 | **Chat completions expose raw exception messages** | `f"Error: {exc}"` leaks internal paths, class names, connection strings to users via HTTP 200. | `chat_completions.py:103-104` |
| 10 | **WebSocket has no authentication** | Any user can observe any task's progress via `/stream/{task_id}`. | `ws.py:16-17` |
| 11 | **`json.loads()` in GitHub API unhandled** | `gh pr view --json` returning non-JSON crashes `get_pr()`. | `github.py:53` |
| 12 | **No max payload size on webhooks** | Memory exhaustion via large JSON payloads. | `webhooks.py:34` |
| 13 | **Stale Docker container references** | Externally-killed containers leave stale references; subsequent operations fail cryptically. | `server.py:20-27` |

### 6.3 Error Propagation Issues

- **Chat completions catch-all** (`chat_completions.py:103-104`): Returns HTTP 200 with `f"Error: {exc}"` in the response body. Clients see a "successful" chat response whose content is a Python exception string. Both misleading (200 status) and leaky (internal details).

- **Langfuse tracing vulnerability** (`tracing.py:47-48`): `langfuse.trace()` and `trace.span()` are outside the try/except block. If Langfuse becomes unreachable after initialization, these calls crash the decorated function.

- **Git timeout propagation** (`server.py:17-27`): `_git()` has a timeout via `asyncio.wait_for` but does NOT catch `TimeoutError`. The exception propagates unhandled to MCP tool handlers.

- **Dead retry config** (`config/models.py:25`): `TierConfig.max_retries` is defined (values 1-5) but **never read by any code path**. Operators configuring retries have their settings silently ignored.

### 6.4 Resilience Test Coverage

**Zero.** Of 48 identified failure modes, not a single one has a test. There are no tests for network failures, timeouts, malformed responses, subprocess failures, WebSocket disconnections, queue overflow, or concurrent access.

---

## 7. Observability & Behavioral Testing Gaps

### 7.1 Logging Infrastructure

- **8 logger instances** across the codebase (structlog-based)
- **13 log emission points** total
- Structured logging is configured via structlog with JSON output
- **No tests verify log output** for any scenario (errors, security events, lifecycle events)

### 7.2 Tracing Infrastructure

The Langfuse tracing decorator (`observability/tracing.py`) is **defined but never applied** to any function. The `@trace` decorator exists but is not imported or used anywhere in the codebase. This means:
- Zero distributed traces are generated in production
- The trace decorator has a bug (Langfuse calls outside try/except) that has never been caught because it's never been executed
- Token and cost tracking (`_extract_usage`) always returns 0 because the response format assumption is wrong

### 7.3 Metrics

**Zero metrics infrastructure.** No Prometheus, no StatsD, no custom counters. There is no way to observe:
- Request rates, latencies, error rates
- Queue depth or processing time
- LLM token usage or costs
- Docker sandbox creation/destruction rates
- Memory or CPU utilization

### 7.4 Health Checking

The `/health` endpoint (`api/health.py`) is a **shallow liveness probe only**. It returns `{"status": "ok"}` unconditionally -- it does not check:
- Database connectivity
- LLM provider reachability
- Docker daemon availability
- Queue health or backlog depth
- Memory/disk pressure

There is no readiness probe endpoint.

### 7.5 Behavioral Test Coverage

**Zero performance or behavioral tests.** The test suite cannot detect:
- Latency regressions
- Memory leaks
- Throughput degradation
- Resource exhaustion patterns
- Queue processing rate changes

---

## 8. Mutation Survivability Analysis

### 8.1 Critical Mutation Survivors

Of the 10 highest-risk mutations analyzed, **7 would survive** (not caught by any test):

| # | Mutation | File | Survives? | Impact |
|---|---|---|---|---|
| 1 | Remove `--cap-drop=ALL` from Docker | `docker.py:117` | **YES** | Container runs with full Linux capabilities |
| 2 | Remove `--network=none` from Docker | `docker.py:118` | **YES** | Sandbox has full network access |
| 3 | Remove `--read-only` from Docker | `docker.py:119` | **YES** | Container filesystem becomes writable |
| 4 | Skip `sanitize_env()` call | `docker.py:99` | **YES** | Secrets leak into sandbox environment |
| 5 | Remove `--memory` limit from Docker | `docker.py:114` | **YES** | Container can consume unlimited memory |
| 6 | Remove `--pids-limit` from Docker | `docker.py:116` | **YES** | Fork bomb possible inside sandbox |
| 7 | Remove webhook signature check | `webhooks.py:19-24` | **YES** | Already dead code -- signature is never verified |
| 8 | Invert `is_dangerous_command()` | `dangerous_tools.py:34` | No | Caught by parametrized tests |
| 9 | Bypass `secret_equal()` timing safety | `secret_equal.py:9` | No | Caught by dedicated tests |
| 10 | Skip `detect_injection()` | `external_content.py:20` | No | Caught by 34 test functions |

**Key insight**: The Docker sandbox security controls are the most mutation-vulnerable code in the system. A single-character change to the Docker `run` command could remove all sandboxing protections, and no test would catch it.

### 8.2 Weak Assertion Patterns

The test suite uses `assert len(...) > 0` in multiple security tests, which passes for any non-empty result regardless of correctness. These assertions should verify specific expected values.

### 8.3 Source Files with Zero Coverage

17 of 30 source files (57%) have **zero test coverage**. Any mutation in these files survives by definition.

---

## 9. Infrastructure & Pipeline Gaps

### 9.1 CI/CD Pipeline

**Status: None exists.** No GitHub Actions, no GitLab CI, no Jenkins, no CircleCI. No Makefile, no tox, no nox, no pre-commit hooks. Tests, linting, and type checking are only run manually.

This means:
- Nothing prevents broken code from being pushed or merged
- The existing test investment provides zero automated protection
- No coverage reporting or enforcement
- No automated quality gates

### 9.2 Current Development Workflow

```
Developer Workstation
  |
  +-- Manual: pytest tests/
  +-- Manual: ruff check src/
  +-- Manual: mypy src/
  |
  git push --> nothing happens
```

### 9.3 Configuration Issues

| Issue | Details |
|---|---|
| **No coverage config** | pytest-cov installed but no `[tool.coverage.run]` section, no `--cov-fail-under` |
| **Dev deps in prod Docker** | Dockerfile installs `.[dev]` (pytest, ruff, mypy) in the production image |
| **Duplicated TestClient fixture** | Copy-pasted across `test_health.py` and `test_tasks.py`; different pattern in `test_webhooks.py` |
| **Overbroad autouse fixture** | `_reset_task_queue` runs for all 141 tests, including 106 that never touch the task queue |

---

## 10. Unified Risk Matrix

Cross-referencing findings from all six analysis dimensions into a single risk matrix:

### CRITICAL (P0) -- Implement immediately

| # | Risk | Dimensions | Location |
|---|---|---|---|
| 1 | **No CI/CD pipeline** -- tests never enforced | Infrastructure, Mutation | Project-level |
| 2 | **LLM call has no timeout/retry/circuit-breaker** -- service outage on provider failure | Chaos, Contract, Behavioral | `conductor.py:135` |
| 3 | **62% of code untested** -- all async paths, conductor, runner, queue, Docker, WS | Coverage, Mutation | 17 source files |
| 4 | **Docker sandbox security flags untested** -- mutation removes `--cap-drop=ALL`, `--network=none`, `--read-only` with no detection | Mutation, Chaos | `docker.py:114-119` |
| 5 | **Webhook signature verification is dead code** -- unauthenticated webhook ingestion | Chaos, Mutation, Contract | `webhooks.py:19-24` |
| 6 | **No coverage configuration or enforcement** | Infrastructure | `pyproject.toml` |

### HIGH (P1) -- Implement within 1-2 sprints

| # | Risk | Dimensions | Location |
|---|---|---|---|
| 7 | **Zero async test coverage** -- conductor, runner, queue, WS all untested | Coverage, Contract | All async modules |
| 8 | **Zero mocking infrastructure** -- cannot unit-test code with external deps | Coverage, Chaos | Project-level |
| 9 | **Chat completions leak exception details** -- `f"Error: {exc}"` via HTTP 200 | Chaos, Contract | `chat_completions.py:103-104` |
| 10 | **Langfuse tracing crashes agent execution** -- observability is a SPOF | Chaos | `tracing.py:47-48` |
| 11 | **Git clone has no timeout** -- hangs indefinitely | Chaos | `server.py:38-43` |
| 12 | **No OpenAI-compat contract tests** -- SSE streaming format, response schema | Contract | `chat_completions.py` |
| 13 | **Path traversal in `is_blocked_path()`** -- no path normalization | Property | `workspace.py:25` |
| 14 | **No pre-commit hooks or Makefile** -- no developer guardrails | Infrastructure | Project-level |
| 15 | **Python version inconsistency** -- .python-version, Dockerfile, runtime disagree | Infrastructure | Multiple files |
| 16 | **Dev deps in production Docker image** | Infrastructure | `Dockerfile:21` |

### MEDIUM (P2) -- Implement within 3-4 sprints

| # | Risk | Dimensions | Location |
|---|---|---|---|
| 17 | **Langfuse tracing decorator is never applied** -- zero distributed traces | Observability | `tracing.py` |
| 18 | **Token/cost tracking returns 0** -- usage data always wrong | Observability | `tracing.py` |
| 19 | **Health check is liveness-only** -- no readiness probe | Observability, Contract | `health.py` |
| 20 | **WebSocket has no authentication** | Chaos, Contract | `ws.py:16-17` |
| 21 | **No property-based tests for security functions** | Property | `security/` modules |
| 22 | **No test timeout enforcement** (no pytest-timeout) | Infrastructure | `pyproject.toml` |
| 23 | **Autouse fixture overbroad** | Infrastructure | `tests/conftest.py` |
| 24 | **No database tests** | Coverage | `tests/memory/` |
| 25 | **`TierConfig.max_retries` is dead config** | Chaos | `config/models.py:25` |
| 26 | **No log output verification tests** | Observability | All log sites |
| 27 | **`_verify_github_signature` untested** (also dead code) | Coverage, Mutation | `webhooks.py:19-24` |
| 28 | **Weak assertions (`len > 0`)** in security tests | Mutation | Multiple test files |

### LOW (P3) -- Backlog

| # | Risk | Dimensions | Location |
|---|---|---|---|
| 29 | **No mutation testing tooling** | Mutation | Project-level |
| 30 | **No contract verification against OpenAI spec** | Contract | `chat_completions.py` |
| 31 | **No chaos/resilience testing framework** | Chaos | Project-level |
| 32 | **No property-based testing framework** | Property | Project-level |
| 33 | **No test randomization** (pytest-randomly) | Infrastructure | `pyproject.toml` |
| 34 | **Docker container name collision** (`id() % 100000`) | Chaos | `docker.py:103` |
| 35 | **No snapshot testing for API responses** | Contract | API test files |

---

## 11. Prioritized Remediation Roadmap

### Phase 1: Foundation (1-2 days) -- Quick Wins

These changes require no new test code and immediately improve the testing infrastructure:

**1.1 Add coverage configuration to `pyproject.toml`:**
```toml
[tool.coverage.run]
source = ["maistro"]
omit = ["*/tests/*"]

[tool.coverage.report]
fail_under = 40
show_missing = true
```
Start at 40% (current estimated level) and ratchet up as tests are added.

**1.2 Add a Makefile:**
```makefile
.PHONY: test lint typecheck check
test:
	pytest tests/ --cov=maistro --cov-report=term-missing
lint:
	ruff check src/ tests/
	ruff format --check src/ tests/
typecheck:
	mypy src/
check: lint typecheck test
```

**1.3 Add pytest-timeout to dev dependencies and configure:**
```toml
# In [tool.pytest.ini_options]
timeout = 30
```

**1.4 Move `_reset_task_queue` fixture** from root `conftest.py` to `tests/api/conftest.py`.

**1.5 Consolidate TestClient fixture** into `tests/api/conftest.py`.

**1.6 Align Python version** to 3.12 across `.python-version`, Dockerfile, and mypy config.

**1.7 Fix Dockerfile** to use multi-stage build separating dev and prod dependencies.

### Phase 2: CI/CD Pipeline (1-2 days)

**2.1 Create GitHub Actions workflow** (`.github/workflows/ci.yml`):
- Stage 1: `ruff check` + `ruff format --check` + `mypy`
- Stage 2: `pytest --cov --cov-fail-under=40`
- Stage 3: Upload coverage report
- Trigger on push and PR

**2.2 Add pre-commit hooks** (`.pre-commit-config.yaml`):
- ruff check + format
- mypy
- trailing whitespace, end-of-file fixer
- detect-secrets

### Phase 3: Critical Test Coverage (3-5 days)

**3.1 Docker sandbox security tests** (addresses Mutation Survivors #1-6):
```python
# tests/tools/test_docker_security.py
# Verify Docker run commands include all security flags:
# --cap-drop=ALL, --network=none, --read-only, --memory, --pids-limit
# Use mock to capture subprocess args and assert flag presence
```

**3.2 Conductor tests with mocked LLM** (addresses Coverage gap for `conductor.py`):
```python
# tests/agents/test_conductor.py
# Mock PydanticAI agent.run() to return known ConductorOutput
# Test: happy path, LLM timeout, validation error (retries), provider error
# Test: dry-run mode
```

**3.3 Task queue and runner tests** (addresses Coverage gap for `queue.py`, `runner.py`):
```python
# tests/tasks/test_queue.py, tests/tasks/test_runner.py
# Test: submit, claim, complete, fail transitions
# Test: queue ordering (FIFO)
# Test: runner processes tasks from queue
# Test: runner handles task failure gracefully
```

**3.4 Wire up and test webhook signature verification** (addresses dead code finding):
```python
# Actually call _verify_github_signature() in the webhook handler
# Test: valid signature passes, invalid signature returns 401
```

### Phase 4: Resilience & Contracts (3-5 days)

**4.1 LLM provider resilience:**
- Add timeout to `agent.run()` calls (e.g., `asyncio.wait_for(..., timeout=120)`)
- Add retry with exponential backoff for transient HTTP errors (429, 502, 503)
- Add tests mocking each failure mode

**4.2 Fix Langfuse tracing vulnerability:**
- Move `langfuse.trace()` and `trace.span()` inside the try/except block
- Add test: mock Langfuse to raise, verify decorated function still succeeds

**4.3 Fix chat completions error handling:**
- Return proper HTTP error status codes instead of 200 with error text
- Sanitize exception messages (no internal details in responses)
- Add tests for error responses

**4.4 OpenAI-compatible contract tests:**
- Verify streaming SSE format (`data: {...}\n\ndata: [DONE]\n\n`)
- Verify non-streaming response schema matches OpenAI spec
- Verify `/v1/models` response format

**4.5 Add timeout to git clone:**
- Wrap `proc.communicate()` in `asyncio.wait_for(..., timeout=120)`
- Add test for timeout behavior

### Phase 5: Advanced Testing (5-10 days, ongoing)

**5.1 Property-based testing:**
- Add `hypothesis` to dev dependencies
- Write property tests for `detect_injection`, `is_dangerous_command`, `sanitize_env`, `secret_equal`, `is_blocked_path`

**5.2 Fix `is_blocked_path()` path traversal:**
- Add `pathlib.Path.resolve()` before prefix checking
- Add hypothesis tests generating adversarial paths

**5.3 Integration tests:**
- Database integration tests with test PostgreSQL
- Docker sandbox integration tests
- End-to-end task lifecycle tests

**5.4 Behavioral/performance baselines:**
- Add pytest-benchmark for critical path functions
- Establish latency baselines for API endpoints
- Add memory profiling for long-running processes

**5.5 Mutation testing:**
- Add `mutmut` to dev dependencies
- Run mutation testing on security modules
- Establish mutation score baseline

---

## Appendix A: File Reference

All source files analyzed in this audit:

```
src/maistro/
├── agents/
│   ├── conductor.py      (137 lines, 0% tested)
│   ├── prompts.py         (57 lines, 0% tested)
│   └── types.py           (58 lines, tested)
├── api/
│   ├── auth.py            (49 lines, tested)
│   ├── chat_completions.py (163 lines, 0% tested)
│   ├── health.py          (23 lines, tested)
│   ├── models.py          (40 lines, tested)
│   ├── tasks.py           (68 lines, tested)
│   ├── webhooks.py        (94 lines, partial)
│   └── ws.py              (63 lines, 0% tested)
├── config/
│   ├── models.py          (60 lines, 0% tested)
│   └── settings.py        (80 lines, 0% tested)
├── memory/
│   └── store.py           (79 lines, 0% tested)
├── observability/
│   └── tracing.py         (62 lines, 0% tested)
├── security/
│   ├── dangerous_tools.py (89 lines, tested)
│   ├── external_content.py (125 lines, tested)
│   ├── secret_equal.py    (33 lines, tested)
│   ├── secure_random.py   (35 lines, tested)
│   └── trust_boundary.py  (121 lines, tested)
├── tasks/
│   ├── models.py          (66 lines, partial)
│   ├── queue.py          (109 lines, 0% tested)
│   ├── runner.py         (104 lines, 0% tested)
│   └── status.py          (43 lines, tested)
├── tools/
│   ├── git/
│   │   ├── github.py      (67 lines, 0% tested)
│   │   └── server.py     (169 lines, 0% tested)
│   └── sandbox/
│       ├── docker.py     (146 lines, 0% tested)
│       ├── env_sanitize.py (85 lines, tested)
│       ├── server.py     (110 lines, 0% tested)
│       └── workspace.py   (43 lines, tested)
└── main.py                (62 lines, 0% tested)
```

## Appendix B: Recommended Chaos Test Scenarios

| Priority | Scenario | Inject | Verify |
|---|---|---|---|
| P0 | LLM provider outage | Mock `agent.run()` -> `ConnectError` | Task fails gracefully, queue continues |
| P0 | LLM infinite hang | Mock `agent.run()` -> `sleep(forever)` | Timeout fires, queue continues |
| P0 | Process restart data loss | Kill process with 10 queued tasks | Document all tasks lost (motivates persistence) |
| P1 | Docker daemon failure | Mock subprocess -> `FileNotFoundError` | Sandbox creation returns clear error |
| P1 | Git clone hangs | Mock `proc.communicate()` -> never returns | Should timeout (currently hangs forever) |
| P1 | Langfuse crashes agent | Mock `langfuse.trace()` -> `ConnectionError` | Agent execution succeeds regardless |
| P1 | Forged GitHub webhook | Send webhook with bad signature | Should be rejected (currently accepted) |
| P2 | Malformed LLM response | Mock PydanticAI -> `ValidationError` | Retries exhaust, task fails cleanly |
| P2 | Exception message leak | Mock `run_task()` -> exception with DB connection string | Response must not contain connection string |
| P2 | Queue flooding | Submit 10,000 tasks rapidly | System should back-pressure or rate-limit |
