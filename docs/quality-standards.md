# Maistro Engine — Code Quality Standards

## Executive Summary

Maistro Engine is an early-stage (Phase 1) multi-agent AI platform with sound architectural intent but significant gaps between design and implementation. The codebase demonstrates clean module boundaries and good use of Pydantic for type safety, but suffers from disconnected subsystems (security, observability, persistence), performance-critical design oversights (fake streaming, single-threaded task execution, no LLM timeouts), and inconsistent API contracts. The five-domain analysis below benchmarks the codebase against industry standards and identifies 58 enforceable rules for ongoing quality enforcement.

### Architecture (Score: 4/10)
The intended layered architecture (API -> Tasks -> Agents -> Tools, with cross-cutting Security/Config/Observability) is sound, but the implementation diverges critically: the entire security module is dead code (zero imports from production paths), the observability layer is disconnected, database persistence is documented but not wired in, and the chat completions endpoint bypasses the task queue entirely, creating two inconsistent execution paths.

### Coupling & Cohesion (Score: 5/10)
Module boundaries are generally reasonable, with stable foundation modules (tasks/models.py, config/settings.py) correctly having zero dependencies. However, bidirectional coupling between agents/ and tasks/ creates a fragile core, module-level singletons impede testing, inline imports in chat_completions.py hide dependencies, and os.environ.get() calls bypass the centralized settings system in 7 locations. The security package has zero afferent coupling from production code — it exists in complete isolation.

### API Surface & Contracts (Score: 4/10)
The OpenAI-compatible API surface is a good design decision for ecosystem integration, but execution is inconsistent: endpoints return 4 different ad-hoc dict shapes instead of typed Pydantic models, error handling is non-uniform (some return HTTPException details, chat completions returns errors as 200 OK), the WebSocket endpoint has no authentication, the GitHub webhook signature verification is defined but never called, and the /result sub-endpoint is an exact duplicate of the main task endpoint.

### Complexity & Cognitive Load (Score: 7/10)
This is the strongest domain. Most functions are short and focused with cyclomatic complexity under 10. The main concerns are the WebSocket handler (cognitive complexity ~12 with 5 nesting levels), the _execute_task function mixing 5+ responsibilities in 55 lines, duplicated code blocks in chat_completions.py, and 11+ magic numbers scattered across the codebase. The codebase is well-positioned to maintain low complexity if thresholds are codified now.

### Performance Patterns (Score: 3/10)
The most concerning domain for an AI API gateway. The streaming endpoint doesn't actually stream (it buffers the full LLM response then chunks the string). The task runner processes exactly one task at a time. LLM calls have no timeout. Settings are re-parsed from disk on every request. Docker sandbox containers are cached in an unbounded dict with no cleanup. The WebSocket uses polling (500ms sleep) instead of event-driven updates. These patterns would cause severe latency amplification and resource exhaustion under any meaningful load.

### Error Handling & Resilience (Score: 3/10)
The codebase has critical gaps in error handling that would cause silent failures and system-wide outages in production. The chat completions endpoint masks all errors as HTTP 200 OK responses with error text embedded in message content — clients cannot distinguish failures from successes. The TaskRunner worker loop will permanently die from a single unhandled exception, silently stopping all task processing. There is no global exception handler, producing inconsistent error contracts (some JSON, some plain text). LLM calls have zero retry logic for transient failures. Docker containers leak on error paths with no cleanup mechanism. The health check always reports "ok" regardless of downstream dependency health. GitHub CLI helpers don't handle timeout or missing binary errors. There is no circuit breaker, no request correlation IDs, and critical error paths (chat_completions) perform no logging at all.

---

## Current State Scorecard

| Domain | Score | Justification |
|--------|-------|---------------|
| Architecture | 4/10 | Sound layered design with 4 disconnected subsystems (security, observability, persistence, scheduler) and a critical layer-bypass in chat completions |
| Coupling & Cohesion | 5/10 | Reasonable module boundaries undermined by bidirectional agent/task coupling, 7 env-bypass locations, and singleton patterns |
| API Surface | 4/10 | Good OpenAI-compat strategy marred by inconsistent response shapes, missing auth on WebSocket/webhooks, and dead verification code |
| Complexity | 7/10 | Functions are generally well-decomposed; main risks are in ws.py nesting, runner.py multi-responsibility, and chat_completions.py duplication |
| Performance | 3/10 | Fake streaming, single-threaded execution, no LLM timeouts, uncapped resource caches, and polling-based WebSocket constitute systemic risk for an API gateway |
| Error Handling | 3/10 | Errors masked as 200 OK, worker loop dies on unhandled exceptions, no global exception handler, no retry logic, no circuit breaker, container resource leaks, health check always "ok" |

**Overall: 4.3/10** — The codebase has a clear architectural vision and clean foundations but the implementation has critical gaps across error handling, performance, and security that would prevent production deployment without remediation.

---

## Top 10 Violations (Ranked by Severity and Blast Radius)

### 1. Security module is entirely dead code (ARCH-001, COUP-003)
**Severity: Critical | Blast radius: Entire system**
The security/ package (trust boundaries, dangerous command detection, prompt injection detection, constant-time comparison) is never imported by any production code path. Sandbox commands execute unchecked, webhook payloads pass directly to LLM prompts without injection scanning, and no permission grants are created per-task.

### 2. Fake streaming in chat completions (PERF-003)
**Severity: Critical | Blast radius: All interactive users**
The SSE streaming endpoint calls `await run_task()` to completion (potentially 10-60+ seconds), then chunks the completed string into 20-character pieces. Users see zero progress during LLM inference. For an AI gateway, this defeats the core value proposition of streaming.

### 3. Single-threaded task runner with no LLM timeout (PERF-004, PERF-007)
**Severity: Critical | Blast radius: All queued task processing**
One worker processes one task at a time. A hung LLM call (no timeout enforced) blocks all task processing indefinitely. With multiple concurrent users or webhook-triggered tasks, head-of-line blocking makes the system unusable.

### 4. Unauthenticated WebSocket and webhook endpoints (API-003, API-004, ARCH-005)
**Severity: Critical | Blast radius: Security perimeter**
The WebSocket `/stream/{task_id}` endpoint has no auth — any client can enumerate task IDs (48-bit entropy) and read task data. The GitHub webhook handler defines signature verification but never calls it. The CI webhook has zero authentication. These are direct paths to data exposure and resource exhaustion.

### 5. Chat completions bypasses the task queue (ARCH-008, COUP-002)
**Severity: Critical | Blast radius: Observability, rate limiting, consistency**
`POST /v1/chat/completions` directly calls `agents.conductor.run_task()` via inline imports, completely bypassing the task queue, state machine, status tracking, and background worker. Chat-originated tasks have no task ID, no progress tracking, no cancellation, and no audit trail.

### 6. Settings re-parsed on every request (PERF-001)
**Severity: Critical | Blast radius: Per-request latency**
`get_settings()` creates a new `Settings()` instance on every call, re-reading the .env file from disk and reconstructing 4 nested settings objects. Called on every authenticated request.

### 7. Unbounded Docker container cache (PERF-002)
**Severity: Critical | Blast radius: Host resource exhaustion**
`_containers` dict in sandbox/server.py grows without bound. Each entry holds a live Docker container (512MB RAM). No TTL, no max-size, no shutdown cleanup. Long-running processes will exhaust host resources.

### 8. Error responses masquerading as success (API-002, PERF-011)
**Severity: Critical | Blast radius: All API consumers**
Chat completions catches exceptions and returns `f"Error: {exc}"` as a 200 OK response with the error text in the message body. Clients cannot distinguish errors from normal completions. No consistent error envelope exists across endpoints.

### 9. Parallel configuration systems (ARCH-002, COUP-001, COUP-007)
**Severity: Major | Blast radius: Configuration reliability**
Seven `os.environ.get()` calls in production code bypass the Pydantic Settings system. Some config is read at import time (frozen), some at request time (live). Testing requires monkeypatching module-level dicts.

### 10. Documented persistence that doesn't exist (ARCH-003)
**Severity: Major | Blast radius: Data durability expectations**
The task queue docstring claims "PostgreSQL persistence" and "surviving restarts via DB recovery." Neither is true — all state is in-memory. TaskRecord, MemoryEntry, and KnowledgeNode models are defined but never imported by production code.

---

## Recommended Remediation Roadmap

### Phase 1: Immediate — Security & Reliability (This Sprint)

Critical security, error handling, and reliability fixes with minimal architectural disruption. Each item is a focused change that can be done independently.

#### Security (S1–S7)

1. **Wire in security checks for sandbox execution** (ARCH-001, ARCH-009, COUP-003): Import and call `is_dangerous_command()` in `sandbox_exec` before executing any command. Call `is_blocked_path()` in `sandbox_read`, `sandbox_write`, `sandbox_glob`, `sandbox_grep` before accessing workspace paths.

2. **Wire in prompt injection detection for webhooks** (ARCH-001, ARCH-011, COUP-003): Import and call `detect_injection()` and `wrap_external_content(content, ContentSource.WEBHOOK)` in `api/webhooks.py` on all user-supplied text (PR titles, issue bodies, commit messages) before interpolating into TaskCreate descriptions.

3. **Call `_verify_github_signature()` in webhook handler** (ARCH-005, API-004, ERR-011): The function exists and is correct — call it with the raw request body, `x_hub_signature_256` header, and a webhook secret loaded from Settings. Return HTTP 403 on failure.

4. **Add authentication to CI webhook** (API-012): Add shared-secret or HMAC authentication to the CI webhook endpoint. Define a Pydantic request model instead of accepting raw `request.json()`.

5. **Add WebSocket authentication** (API-003): Validate bearer token via query parameter or first message before calling `websocket.accept()`. Return `websocket.close(code=4001)` on failure.

6. **Use `secret_equal()` in auth module** (ARCH-012): Replace `hmac.compare_digest()` in `api/auth.py` with the existing `secret_equal()` from `maistro.security.secret_equal`, which adds HMAC-SHA256 length-leakage protection.

7. **Add request body size limits on webhook endpoints** (PERF-009): Add Content-Length check or body size middleware to prevent multi-GB payload reads into memory.

#### Error Handling (E1–E10)

8. **Fix error masking in chat completions** (ERR-001, API-002, PERF-011): Replace bare `except Exception as exc: response_text = f"Error: {exc}"` with specific exception catches, proper logging with stack trace, and HTTP error status codes (502 for upstream LLM failure, 504 for timeout, 500 for unexpected) with structured JSON error body.

9. **Add global exception handler to FastAPI app** (ERR-003, API-002): Register `@app.exception_handler(Exception)` that logs with structlog (including request context and traceback) and returns JSON with consistent schema `{"error": {"type": "...", "message": "...", "request_id": "..."}}`.

10. **Make TaskRunner worker loop resilient to task failures** (ERR-002): Wrap `await self._execute_task(task_id)` in a `try/except Exception` that logs the error and continues the while loop, preventing a single task failure from killing the background processor.

11. **Add TimeoutError and FileNotFoundError handling to git/github CLI helpers** (ERR-004, ERR-012): Wrap `asyncio.wait_for()` in try/except TimeoutError in both `_git()` and `_run_gh()`. Handle FileNotFoundError from `asyncio.create_subprocess_exec()` when git/gh binaries are missing. Add timeout to `git_clone()`.

12. **Add JSONDecodeError handling to GitHub CLI output parsing** (ERR-004): Wrap `json.loads(output)` calls in `get_pr()` and `list_issues()` with try/except JSONDecodeError, returning structured error dict instead of crashing on malformed gh output.

13. **Narrow sandbox exec exception handling** (ERR-008): Replace bare `except Exception` in `SandboxContainer.exec()` with targeted catches for subprocess-related exceptions (OSError, subprocess.SubprocessError). Re-raise or log infrastructure failures (FileNotFoundError for Docker binary, PermissionError for Docker socket) distinctly from command failures.

14. **Add logging to TaskQueue.update_status() rejection path** (ERR-009): Log a warning with structlog when a state transition is rejected, including current state, requested state, and task_id. Have callers in runner.py check the return value.

15. **Add WebSocket error handling and connection timeout** (ERR-010): Catch Exception in addition to WebSocketDisconnect, send close frame with error code on unexpected errors, and log. Add `asyncio.timeout()` to limit maximum WebSocket session duration.

16. **Add LLM retry logic with exponential backoff** (ERR-007): Wrap `agent.run(prompt)` in retry logic that catches provider-specific exceptions (connection errors, HTTP 429, timeouts) with exponential backoff and jitter. Raise domain-specific `LLMProviderError` after exhausting retries.

17. **Add LLM timeout** (PERF-007): Wrap `agent.run()` with `asyncio.wait_for(timeout=tier_config.timeout)` with per-tier configurable timeouts.

#### Configuration & Correctness (C1–C4)

18. **Cache settings** (PERF-001): Add `@functools.lru_cache()` to `get_settings()` to prevent re-parsing .env from disk on every authenticated request.

19. **Fix misleading docstrings** (ARCH-003): Correct the "PostgreSQL persistence" and "surviving restarts via DB recovery" claims in `queue.py` to "In-memory only (Phase 1)."

20. **Move inline imports to top-level** (COUP-006): Replace the inline `from maistro.agents.conductor import run_task` inside function bodies in `chat_completions.py` with top-level imports. No circular dependency requires deferred imports.

21. **Replace magic numbers with named constants** (CMPLX-006): Define named constants for the 11+ unexplained numeric literals: `STREAM_CHUNK_SIZE = 20`, `DESCRIPTION_LOG_PREVIEW_LEN = 80`, `WEBHOOK_BODY_PREVIEW_LEN = 500`, `WS_POLL_INTERVAL = 0.5`, `WORKER_POLL_TIMEOUT = 1.0`, `SANDBOX_MAX_OUTPUT = 100000`, `EMBEDDING_DIMENSION = 1536`, `PERMISSION_MAX_INPUT = 50000`, `PERMISSION_TTL = 3600`.

---

### Phase 2: Performance & API Consistency (This Quarter)

Moderate refactoring for performance, consistent API contracts, and code quality tooling.

#### Performance (P1–P7)

22. **Implement real streaming** (PERF-003): Replace the fake streaming pattern (buffer full response, chunk string) with Pydantic AI's `agent.run_stream()` or equivalent async iterator yielding tokens as generated.

23. **Route chat completions through the task queue** (ARCH-008, COUP-002): Eliminate the dual execution path. `POST /v1/chat/completions` should submit a TaskCreate to the queue and stream results, providing task ID, progress tracking, and cancellation.

24. **Add concurrent workers to TaskRunner** (PERF-004): Accept `max_workers` parameter, spawn N concurrent asyncio.Tasks or use a Semaphore to process tasks in parallel instead of one-at-a-time sequential execution.

25. **Replace WebSocket polling with asyncio.Event** (PERF-005): TaskQueue exposes an asyncio.Event per task_id. `update_status()` signals it. WebSocket handler awaits the event instead of `asyncio.sleep(0.5)`.

26. **Cache stateless AI agent instances** (PERF-006): Decorate `build_conductor()` with `@lru_cache()` or cache agents by `(model, base_url)` tuple to avoid re-compiling schemas and re-registering tools on every task.

27. **Fix task store list operations** (PERF-008): Replace `list(self._tasks.values())[-limit:]` with OrderedDict with max size, `itertools.islice()`, or DB-backed storage. Add pruning for completed/failed tasks to prevent unbounded growth.

28. **Make Langfuse flush non-blocking** (PERF-012): Replace synchronous `langfuse.flush()` in the async `trace_agent` finally block with `asyncio.to_thread(langfuse.flush)`, a background task, or rely on the SDK's background flush.

#### API Contracts (A1–A8)

29. **Type all API responses with Pydantic models** (API-001): Replace dict returns in POST /tasks, DELETE /tasks, webhooks, and health with typed Pydantic response models so OpenAPI spec shows real schemas instead of "object."

30. **Add consistent error envelope** (API-002, ERR-003): Define `ErrorResponse` model with `error`, `code`, `detail`, and `request_id` fields. All error responses (HTTPException, global handler, streaming errors) use this schema.

31. **Remove or differentiate redundant /result endpoint** (API-005): GET /tasks/{task_id} and GET /tasks/{task_id}/result have identical implementations. Remove /result, or differentiate it (return only TaskResult, add long-polling, etc.).

32. **Add cursor-based pagination to GET /tasks** (API-006): Accept cursor + limit parameters, return PaginatedResponse with items, next_cursor, and total count instead of bare list.

33. **Extract duplicated chat_completions pipeline** (API-007, CMPLX-005): The two identical 7-line blocks (user message extraction → TaskCreate → run_task → exception handling) at lines 91-104 and 143-156 should be a single async function called by both streaming and non-streaming paths.

34. **Define WebSocket message schemas as Pydantic models** (API-008): Create WSProgressMessage, WSResultMessage, WSErrorMessage models instead of ad-hoc dict construction in ws.py.

35. **POST /tasks should return full TaskResponse** (API-011): Return full TaskResponse (HTTP 202) with Location header instead of partial `{"task_id": str, "status": str}` dict that forces an unnecessary round-trip.

36. **Health endpoint: typed model + single version source** (API-009): Define HealthResponse Pydantic model. Read version from `importlib.metadata` or `__version__` constant instead of two independent hardcoded "0.1.0" strings in health.py and main.py.

#### Container & Resource Management (R1–R2)

37. **Implement Docker container cleanup** (PERF-002, ERR-005): Add `__aenter__`/`__aexit__` to SandboxContainer calling `destroy()` on exit. Add TTL-based eviction or periodic reaper for the `_containers` dict. Add lifespan shutdown hook to destroy all containers. Make `destroy()` check and log the exit code of `docker rm -f`.

38. **Consolidate all environment variable access into Settings** (ARCH-002, COUP-001, COUP-007, CMPLX-007, PERF-010): Move all `os.environ.get()` calls from `agents/conductor.py` and `config/models.py` into Pydantic Settings fields. Make `DEFAULT_TIERS` a computed property or lazy function instead of module-level frozen dict.

#### Code Quality Tooling (T1–T3)

39. **Configure complexity linting thresholds** (CMPLX-001, CMPLX-002, CMPLX-003): Add ruff or flake8 rules enforcing cyclomatic complexity ≤ 10, cognitive complexity ≤ 15, and nesting depth ≤ 3 levels. Add to CI pipeline.

40. **Add duplicate code detection** (CMPLX-005): Configure jscpd or pylint duplicate-code checker. Current violations: chat_completions.py dual pipeline blocks.

41. **Consolidate duplicate TaskCreate construction** (COUP-010): TaskCreate is constructed in 6 locations across 3 files with inconsistent field population. Create factory functions per entry point. Have runner.py store original TaskCreate instead of reconstructing from TaskResponse.

---

### Phase 3: Structural Architecture (Next Quarter)

Architectural improvements for multi-agent scaling, testability, and production operations.

#### Architecture (AR1–AR6)

42. **Break bidirectional agent/task coupling** (ARCH-006): Inject executor as a callable into TaskRunner instead of importing `agents.conductor.run_task` directly. Neither module should import the other.

43. **Replace module-level singletons with dependency injection** (ARCH-007, COUP-004): Instantiate TaskQueue in lifespan, store in `app.state`. Inject via `Depends()`. Replace `_containers` global dict with an injected SandboxManager. Tests create fresh instances instead of mutating private variables.

44. **Connect database persistence** (ARCH-003): Wire TaskRecord to the queue via SQLAlchemy sessions. Implement recovery on startup — reload incomplete tasks from database. Add database connection pooling.

45. **Apply observability tracing to conductor pipeline** (ARCH-004): Decorate `run_task()` with `@trace_agent("conductor")`. Trace all LLM-calling functions. Connect to Langfuse instance provisioned in docker-compose.yml.

46. **Decompose _execute_task into pipeline** (CMPLX-004, CMPLX-011, COUP-005): Extract the 6 sequential `update_status()` / `update_progress()` calls and fake REVIEWING/TESTING phases into a named pipeline function. _execute_task should only orchestrate.

47. **Extract model resolution from conductor** (COUP-009): Move `_resolve_model()` and provider URL logic from `agents/conductor.py` to `config/model_resolver.py`. Conductor should not contain infrastructure concerns (os.environ reads, URL manipulation).

#### Resilience Patterns (RP1–RP3)

48. **Implement circuit breaker for LLM provider** (ERR-007): Add circuit breaker pattern that stops hammering a failing LLM provider after N consecutive failures. Open circuit returns fast failure. Half-open circuit tests recovery. Prevents cascading resource exhaustion during outages.

49. **Add health check dependency probes** (ERR-006): Health endpoint probes Docker daemon (`docker info`), LLM provider (HTTP ping), and database (connection test) with short timeouts. Returns `{"status": "degraded", "checks": {...}}` when any probe fails. Add separate `/health/live` for unconditional liveness.

50. **Add graceful shutdown** (NEW): Register shutdown hooks in FastAPI lifespan to: stop accepting new tasks, drain in-progress tasks with timeout, destroy all sandbox containers, flush observability data, close database connections.

#### Code Structure (CS1–CS4)

51. **Decompose WebSocket handler** (CMPLX-012): Extract `_has_state_changed()`, `_build_update_message()`, `_is_terminal()` helpers from the stream_task function to reduce cognitive complexity from ~12 to <8.

52. **Isolate large pattern data from behavioral code** (CMPLX-009): Move `_DANGEROUS_COMMAND_PATTERNS` (22 patterns) and `_INJECTION_PATTERNS` (27 patterns) to separate `security/patterns.py` data file.

53. **Integrate or remove orphan modules** (COUP-008): `memory/store.py`, `observability/tracing.py`, and `scheduler/__init__.py` have zero imports from production code. Either wire them in (tracing → #45, persistence → #44) or move to `_experimental/` directory or delete.

54. **Implement MCP structured returns** (API-010): Replace plain string returns from all 16 MCP tools with dicts containing explicit fields: `{"exit_code": int, "stdout": str, "success": bool}`. Stop requiring agents to parse formatted strings.

55. **Prune unused hard dependencies** (ARCH-010): Move playwright and apscheduler to optional dependency groups in pyproject.toml until Phase 2 features use them. Add docstrings to empty placeholder `__init__.py` files or remove them.

---

### Phase 4: Production Operations (Pre-Launch)

Operational infrastructure required for production deployment that is not covered by any existing code or rule.

#### Testing & CI (CI1–CI4)

56. **Establish test infrastructure and coverage baseline** (NEW): Set up pytest with async support, fixtures for TaskQueue/SandboxContainer/mock LLM, and code coverage measurement. Target ≥80% line coverage for core modules (tasks/, agents/, api/).

57. **Add integration tests for critical paths** (NEW): End-to-end tests for: task submission → queue → conductor → completion, webhook → task creation, chat completions streaming, WebSocket progress streaming. Test error paths (LLM timeout, Docker failure, invalid input).

58. **Configure CI/CD pipeline** (NEW): GitHub Actions (or equivalent) running: lint (ruff), type check (mypy), complexity checks (#39), unit tests, integration tests, Docker image build. Gate merges on all checks passing.

59. **Add load testing benchmarks** (NEW): Establish baseline performance metrics using locust or k6: requests/sec for chat completions, concurrent task throughput, WebSocket connection capacity, P99 latency under load. Track regressions.

#### Observability & Operations (O1–O5)

60. **Add request correlation IDs** (NEW): Generate unique request ID per HTTP request (middleware). Propagate through task queue, conductor, tool calls, and logs. Include in all error responses and log entries. Essential for production debugging.

61. **Configure structured logging** (NEW): Ensure all modules use structlog consistently with JSON output. Add request context (request_id, task_id, user) to all log entries. Configure log levels per module. Set up log aggregation (stdout → collector → storage).

62. **Add monitoring and alerting** (NEW): Expose Prometheus metrics: request latency histograms, task queue depth gauge, worker loop health, LLM call success/failure rates, Docker container count, error rates by endpoint. Configure alerting thresholds.

63. **Add rate limiting** (NEW): Per-client rate limiting on API endpoints (especially chat completions and task submission). Configure via Settings. Return HTTP 429 with Retry-After header. Prevent resource exhaustion from runaway clients or misconfigured integrations.

64. **Add CORS configuration** (NEW): Review and configure CORS middleware for production deployment. Restrict allowed origins, methods, and headers. Currently no CORS middleware exists — cross-origin requests will fail or be unrestricted depending on deployment.

#### Data & Security (DS1–DS4)

65. **Implement secrets management** (NEW): Move all secrets (API keys, webhook secrets, database credentials) from .env file to a proper secrets backend (environment variables from orchestrator, HashiCorp Vault, AWS Secrets Manager). Ensure secrets are never logged.

66. **Add database connection pooling** (NEW): Configure SQLAlchemy async engine with connection pooling (pool_size, max_overflow, pool_recycle). Add health check query. Handle connection exhaustion gracefully.

67. **Container security hardening** (NEW): Run sandbox containers with minimal privileges: `--read-only` root filesystem where possible, `--security-opt no-new-privileges`, memory limits (`--memory`), CPU limits (`--cpus`), network restrictions (`--network none` or restricted bridge). Drop all capabilities except required ones.

68. **API versioning strategy** (NEW): Define versioning approach (URL path `/v1/`, header, or query param) and backward compatibility policy. Current `/v1/` prefix exists but no mechanism for deprecation, version negotiation, or migration.

---

### Summary

| Phase | Items | Focus | Timeline |
|-------|-------|-------|----------|
| Phase 1: Immediate | 21 items (S1–S7, E1–E10, C1–C4) | Security holes, error handling, configuration | This Sprint |
| Phase 2: Performance & API | 20 items (P1–P7, A1–A8, R1–R2, T1–T3) | Streaming, concurrency, typed contracts, tooling | This Quarter |
| Phase 3: Structural | 14 items (AR1–AR6, RP1–RP3, CS1–CS4) | Architecture, resilience, code structure | Next Quarter |
| Phase 4: Operations | 13 items (CI1–CI4, O1–O5, DS1–DS4) | Testing, CI/CD, monitoring, security hardening | Pre-Launch |
| **Total** | **68 items** | | |

Each item references the specific rule IDs it addresses. The 70 rules from the enforcement framework map to these 68 remediation items, with some rules addressed by a single item and some items addressing multiple related rules. The 13 items in Phase 4 address production concerns not covered by any existing rule — these represent operational infrastructure that the current codebase has zero implementation for.
