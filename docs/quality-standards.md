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

### Phase 1: Immediate (This Sprint)

These are the changes that address critical security and reliability gaps with minimal architectural disruption.

1. **Wire in security checks**: Import and call `is_dangerous_command()` in sandbox_exec, `detect_injection()` + `wrap_external_content()` in webhooks, `is_blocked_path()` in sandbox file operations
2. **Call `_verify_github_signature()`**: It's already written — just call it in the handler
3. **Add WebSocket authentication**: Check bearer token before `websocket.accept()`
4. **Cache settings**: Add `@lru_cache()` to `get_settings()`
5. **Add LLM timeout**: Wrap `agent.run()` with `asyncio.wait_for()`
6. **Fix error handling in chat completions**: Return proper HTTP errors instead of 200 OK with error text
7. **Fix docstrings**: Correct the "PostgreSQL persistence" claim in queue.py

### Phase 2: Short-term (This Quarter)

These improve performance and API consistency, requiring moderate refactoring.

8. **Implement real streaming**: Use Pydantic AI's `agent.run_stream()` in chat_completions
9. **Route chat completions through the task queue**: Eliminate the dual execution path
10. **Add concurrent workers to TaskRunner**: Accept `max_workers` parameter, spawn N worker tasks
11. **Replace WebSocket polling with asyncio.Event**: Event-driven instead of sleep(0.5)
12. **Consolidate configuration**: Move all os.environ.get() calls into Settings; make DEFAULT_TIERS a computed property
13. **Type all API responses**: Replace dict returns with Pydantic models
14. **Add consistent error envelope**: Global exception handler with ErrorResponse model
15. **Implement container cleanup**: Add TTL-based eviction for sandbox containers, shutdown hook
16. **Add cursor-based pagination**: Replace list slicing in list_tasks()

### Phase 3: Structural (Ongoing)

These are architectural improvements that lay groundwork for Phase 2 multi-agent capabilities.

17. **Break bidirectional agent/task coupling**: Inject executor as a callable into TaskRunner
18. **Replace module-level singletons with DI**: Store TaskQueue in app.state, inject via Depends()
19. **Connect database persistence**: Wire TaskRecord to the queue, implement recovery on startup
20. **Apply observability tracing**: Decorate conductor pipeline with @trace_agent
21. **Decompose _execute_task**: Extract phase transitions into pipeline abstraction
22. **Extract model resolution from conductor**: Move to config/model_resolver.py
23. **Implement MCP structured returns**: Return dicts/models instead of formatted strings from tools
24. **Add request body size limits**: Middleware for webhook endpoints
25. **Prune unused dependencies**: Move playwright/apscheduler to optional deps until Phase 2
