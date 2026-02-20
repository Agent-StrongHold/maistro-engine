# Maistro Engine — Code Quality Enforcement Standards

## How to Use This Document

This document is an authoritative evaluation framework for the Maistro Engine codebase. When reviewing code, evaluating pull requests, or making architectural decisions, Claude should:

1. **Load this document** at the start of any code review session for this repository
2. **Apply every applicable rule** from the Standard Rules section below to the files being reviewed
3. **Make binary pass/fail determinations** — each rule has explicit Pass and Fail criteria; do not invent intermediate states
4. **Report violations by rule ID** (e.g., "ARCH-001 violation: sandbox_exec calls container.exec() without is_dangerous_command() check")
5. **Assess severity** — critical violations must be flagged as blocking; major violations should be flagged as required changes; minor violations are advisory
6. **Check for waivers** — if a violation appears intentional, follow the Waiver Process at the end of this document
7. **Evaluate new code against the same standards** — these rules apply to both existing code and all new contributions

Rules are organized by domain prefix:
- **ARCH-###**: Architectural patterns and module boundaries
- **COUP-###**: Coupling, cohesion, and dependency management
- **API-###**: API surface, contracts, and interface design
- **CMPLX-###**: Complexity thresholds and cognitive load
- **PERF-###**: Performance patterns and resource management
- **TEST-###**: Testing quality and coverage requirements

---

## Standard Rules

### ARCH-001: Security module must be integrated into all modules handling untrusted input or executing external commands
**Severity:** critical
**Rationale:** The security/ package (trust_boundary.py, dangerous_tools.py, external_content.py, secret_equal.py, secure_random.py) is never imported by any production code path outside security/ itself. The trust_boundary permission system is never checked before agent execution. The dangerous_tools blocklist is never consulted before sandbox_exec or git operations. The external_content prompt-injection detector is never applied to webhook payloads, user messages, or PR bodies.
**Pass:** tasks/runner.py calls create_grant_for_task() and passes the grant into the conductor; sandbox_exec checks is_dangerous_command() before executing; api/webhooks.py and api/chat_completions.py call detect_injection() on all user-supplied text; tools/sandbox/server.py calls is_blocked_path() on workspace paths and is_dangerous_command() on commands before execution.
**Fail:** `grep "from maistro.security" src/maistro/` outside security/ returns zero results. tools/sandbox/server.py:41 calls container.exec(command) without calling is_dangerous_command(command). api/webhooks.py:34 processes payload with no call to detect_injection().
**Automated check available:** yes — grep for `from maistro.security` imports in api/, tasks/, tools/ directories

---

### ARCH-002: All environment variable access must go through config/ module
**Severity:** major
**Rationale:** agents/conductor.py uses os.environ.get() for LITELLM_BASE_URL, OLLAMA_BASE_URL, MAISTRO_DRY_RUN. config/models.py uses os.environ.get() for tier model names at module load time. This creates two parallel configuration systems — Pydantic Settings (validated, typed) and raw os.environ (unvalidated, invisible to settings object).
**Pass:** LITELLM_BASE_URL, OLLAMA_BASE_URL, MAISTRO_DRY_RUN, and MAISTRO_TIER_*_MODEL are all fields on Settings or a sub-config class. No os.environ.get() calls exist outside config/.
**Fail:** agents/conductor.py:35 — `os.environ.get("LITELLM_BASE_URL", "")`. config/models.py:36 — `os.environ.get("MAISTRO_TIER_1_MODEL", "ollama/qwen2.5-coder:7b")`.
**Automated check available:** yes — grep for `os.environ` outside config/

---

### ARCH-003: Database persistence must be connected or documented as absent
**Severity:** major
**Rationale:** tasks/queue.py docstring claims "In-memory task queue with PostgreSQL persistence" and "surviving restarts via DB recovery." Neither is true. TaskRecord in memory/store.py is never imported by production code. All task state is in-memory and lost on restart.
**Pass:** Either queue.py persists to PostgreSQL using TaskRecord, or the docstring is corrected to "In-memory only (Phase 1)."
**Fail:** tasks/queue.py:1-5 claims PostgreSQL persistence; `grep "TaskRecord" src/` returns only memory/store.py. No SQLAlchemy engine/session is created anywhere.
**Automated check available:** partial — grep for "TaskRecord" imports and SQLAlchemy session usage

---

### ARCH-004: Observability tracing must be applied to the conductor pipeline
**Severity:** major
**Rationale:** observability/tracing.py defines trace_agent() decorator but it is never imported or applied to any function. Langfuse is provisioned in docker-compose.yml and configured in settings.py, but zero observability data is generated.
**Pass:** agents/conductor.py applies @trace_agent("conductor") to run_task(). All LLM-calling functions are traced.
**Fail:** `grep "trace_agent" src/` outside observability/ returns zero results. agents/conductor.py:79 has no tracing decorator.
**Automated check available:** yes — grep for trace_agent usage

---

### ARCH-005: Webhook endpoints must authenticate requests using signature verification
**Severity:** critical
**Rationale:** api/webhooks.py:19 defines _verify_github_signature() but the github_webhook handler never calls it. Any POST to /webhooks/github injects tasks into the queue unauthenticated. ci_webhook has no auth at all.
**Pass:** github_webhook calls _verify_github_signature() and returns 401 on failure. ci_webhook has equivalent auth.
**Fail:** api/webhooks.py:28-69 — handler body never references _verify_github_signature. Neither endpoint uses RequireAuth.
**Automated check available:** yes — grep for _verify_github_signature call sites

---

### ARCH-006: Cross-layer imports between agents/ and tasks/ must flow in one direction
**Severity:** major
**Rationale:** agents/conductor.py imports tasks.models.TaskCreate. tasks/runner.py imports agents.conductor.run_task. This bidirectional dependency means neither module can be tested or replaced independently.
**Pass:** tasks/runner.py depends on an injected Callable rather than importing agents.conductor directly, OR agents/conductor.py receives task data as plain parameters.
**Fail:** tasks/runner.py:10 — `from maistro.agents.conductor import run_task`. agents/conductor.py:20 — `from maistro.tasks.models import TaskCreate`.
**Automated check available:** yes — check import directions between agents/ and tasks/

---

### ARCH-007: Singleton TaskQueue must use dependency injection instead of module-level global
**Severity:** minor
**Rationale:** tasks/queue.py:102 uses module-level _queue variable. conftest.py directly mutates this private variable to reset state. No DI mechanism exists despite the comment "Singleton — replaced by DI in production."
**Pass:** TaskQueue instantiated in lifespan, stored in app.state. Tests create fresh instances.
**Fail:** tasks/queue.py:102 — `_queue: TaskQueue | None = None` with `global _queue` in get_task_queue().
**Automated check available:** partial — grep for `global _queue`

---

### ARCH-008: Chat completions must not bypass the task queue via deferred inline imports
**Severity:** major
**Rationale:** POST /v1/chat/completions directly calls agents.conductor.run_task() via deferred imports (lines 91-92, 143-144), completely bypassing task queue, state machine, status tracking, and background worker. Creates two inconsistent execution paths.
**Pass:** chat_completions submits TaskCreate to queue via queue.submit() and streams results.
**Fail:** api/chat_completions.py:91-92 — `from maistro.agents.conductor import run_task` inside function body. Same at lines 143-144.
**Automated check available:** yes — grep for inline imports of agents.conductor in api/

---

### ARCH-009: Sandbox tools must apply workspace validation and command safety checks
**Severity:** major
**Rationale:** tools/sandbox/server.py:41 passes commands directly to container.exec() with no safety checks. No import from maistro.security exists anywhere in tools/.
**Pass:** sandbox_exec calls is_dangerous_command() before execution. sandbox_read/write validate paths via is_blocked_path(). sandbox_grep/glob sanitize patterns.
**Fail:** tools/sandbox/server.py:40 — `container.exec(command, timeout=timeout)` with no prior safety check.
**Automated check available:** yes — grep for security imports in tools/

---

### ARCH-010: Empty placeholder modules must contain a docstring or be removed
**Severity:** minor
**Rationale:** browser/__init__.py, media/__init__.py, scheduler/__init__.py are empty. playwright and apscheduler are installed as hard dependencies with no code. Developers cannot distinguish "not built" from "built but empty."
**Pass:** Placeholders contain a module-level docstring, OR are removed with dependencies moved to optional group.
**Fail:** Three empty __init__.py files with no content. pyproject.toml:31-34 installs playwright/apscheduler.
**Automated check available:** yes — check file content of placeholder __init__.py files

---

### ARCH-011: Webhook payloads must be sanitized before injection into task descriptions
**Severity:** critical
**Rationale:** api/webhooks.py interpolates raw PR titles, issue titles, and issue bodies into TaskCreate.description, which is fed to the LLM. A malicious issue body with prompt injection goes directly into the LLM prompt. security/external_content.py was built for this but is never used.
**Pass:** webhooks.py wraps content with wrap_external_content(content, ContentSource.WEBHOOK) and calls detect_injection().
**Fail:** api/webhooks.py:49 — `f"Review PR #{number}: {title} in {repo}"` with raw title. Line 64 interpolates body_text[:500] directly.
**Automated check available:** yes — grep for wrap_external_content in api/webhooks.py

---

### ARCH-012: Auth module must use security/secret_equal.py instead of reimplementing HMAC comparison
**Severity:** minor
**Rationale:** api/auth.py:38 uses hmac.compare_digest() directly. security/secret_equal.py provides secret_equal() with additional protections (HMAC-SHA256 to prevent length leakage, type confusion defense). Security primitives should not be duplicated.
**Pass:** api/auth.py imports and uses secret_equal() from maistro.security.secret_equal.
**Fail:** api/auth.py:1 — `import hmac`, line 38 — `hmac.compare_digest(token.encode(), key.encode())`.
**Automated check available:** yes — check auth.py imports

---

### COUP-001: All environment variable access must go through Pydantic Settings
**Severity:** critical
**Rationale:** config/models.py (lines 36-58) and agents/conductor.py (lines 35, 41, 91) read os.environ directly, creating a parallel configuration system untestable without monkeypatching os.environ.
**Pass:** Every configuration value accessed through a Settings subclass field. os.environ appears nowhere outside config/settings.py.
**Fail:** config/models.py:36 — `os.environ.get("MAISTRO_TIER_1_MODEL", ...)` at module level. agents/conductor.py:35 — `os.environ.get("LITELLM_BASE_URL", "")`.
**Automated check available:** yes — grep for os.environ outside config/

---

### COUP-002: API layer must not import or call agent functions directly
**Severity:** critical
**Rationale:** api/chat_completions.py inline-imports and directly calls agents/conductor.run_task(), bypassing the task queue. Queue's status tracking, progress reporting, and error handling are all skipped for chat completions.
**Pass:** api/chat_completions.py submits TaskCreate to queue, only tasks/runner.py calls run_task().
**Fail:** api/chat_completions.py:91-92 — `from maistro.agents.conductor import run_task` inside function body.
**Automated check available:** yes — grep for conductor imports in api/

---

### COUP-003: Security package must be integrated into execution pipeline
**Severity:** critical
**Rationale:** The entire security/ package has Ca=0 from outside the package. No module in agents/, tasks/, tools/, or api/ imports from security/. Sandbox executes arbitrary commands unchecked, webhooks pass payloads directly to LLM prompts.
**Pass:** tools/sandbox/server.py calls is_dangerous_command(); api/webhooks.py calls wrap_external_content(); agents/conductor.py creates PermissionGrant.
**Fail:** `grep -r "from maistro.security" src/maistro/` outside security/ returns zero results.
**Automated check available:** yes — grep for security imports

---

### COUP-004: Module-level mutable singletons must be replaced with dependency injection
**Severity:** major
**Rationale:** tasks/queue.py:102-109 has module-level _queue singleton. tools/sandbox/server.py:20 has module-level _containers dict. These prevent parallel testing, isolated instances, and clean state reset.
**Pass:** TaskQueue created in lifespan, stored in app.state. _containers managed by an injected SandboxManager.
**Fail:** tasks/queue.py:102 — `_queue: TaskQueue | None = None`. tools/sandbox/server.py:20 — `_containers: dict[str, SandboxContainer] = {}`.
**Automated check available:** partial — grep for module-level mutable globals

---

### COUP-005: Task runner must not manually drive state transitions
**Severity:** major
**Rationale:** tasks/runner.py _execute_task calls update_status() 5 times in sequence, manually encoding transition order already defined in status.py TRANSITIONS. REVIEWING and TESTING phases are fake pass-throughs updating status without work.
**Pass:** TaskQueue exposes a pipeline progression method; runner calls a single high-level method.
**Fail:** tasks/runner.py:56-91 — five sequential update_status() calls with hardcoded TaskStatus values.
**Automated check available:** partial — count update_status calls in runner.py

---

### COUP-006: Inline function-body imports of internal modules must be replaced with top-level imports
**Severity:** major
**Rationale:** api/chat_completions.py uses inline imports at lines 91-92 and 143-144. No circular dependency requires it. Hides dependencies from static analysis, duplicates import statements.
**Pass:** All internal maistro.* imports at top of file. Inline imports only for optional third-party deps.
**Fail:** api/chat_completions.py:91 — `from maistro.agents.conductor import run_task` inside function body. Same at line 143.
**Automated check available:** yes — AST analysis for function-body imports of maistro.*

---

### COUP-007: Stable foundation modules must not contain concrete runtime configuration
**Severity:** major
**Rationale:** config/models.py (I=0.00, maximally stable) contains DEFAULT_TIERS dict with hardcoded os.environ.get() calls frozen at import time. Violates Stable Abstractions Principle.
**Pass:** config/models.py exports only Tier enum and TierConfig model. DEFAULT_TIERS is a function or Settings property.
**Fail:** config/models.py:33-60 — DEFAULT_TIERS constructed at module level using os.environ.get() four times.
**Automated check available:** yes — check for os.environ in config/models.py

---

### COUP-008: Every module must be imported by at least one production module
**Severity:** minor
**Rationale:** memory/store.py, observability/tracing.py, and scheduler/__init__.py are orphan modules with Ca=0 from production code. They create the illusion of capability that doesn't exist.
**Pass:** Orphan modules are either integrated or moved to _experimental/ directory or deleted.
**Fail:** `grep "from maistro.memory"` and `grep "from maistro.observability"` return zero results from production code.
**Automated check available:** yes — cross-reference imports with source files

---

### COUP-009: agents/conductor.py must not contain infrastructure concerns
**Severity:** major
**Rationale:** conductor.py (Ca=2, Ce=4, I=0.60) combines model/provider resolution (reading env vars, URL routing), agent construction, and task orchestration. _resolve_model() is pure infrastructure that belongs in config/.
**Pass:** A config/model_resolver.py handles resolve_model(). conductor.py only handles agent logic.
**Fail:** agents/conductor.py:30-47 — _resolve_model() reading os.environ.get("LITELLM_BASE_URL") and performing string manipulation.
**Automated check available:** partial — check for os.environ and URL logic in agents/

---

### COUP-010: Duplicate TaskCreate construction must be consolidated
**Severity:** major
**Rationale:** TaskCreate is constructed in 6 locations across 3 files (chat_completions.py x2, webhooks.py x3, runner.py x1). chat_completions sets no workspace/tier/constraints. runner.py reconstructs from TaskResponse, losing constraints and branch.
**Pass:** Each entry point has a single factory function for TaskCreate. runner.py stores original TaskCreate.
**Fail:** api/chat_completions.py:99 and :151 — duplicate `TaskCreate(description=user_msg or 'No task specified')`.
**Automated check available:** partial — count TaskCreate() constructor calls

---

### API-001: Every REST endpoint must return a typed Pydantic response model
**Severity:** major
**Rationale:** POST /tasks returns dict[str, str], DELETE /tasks returns dict[str, bool], webhooks return dict[str, Any], health returns dict[str, Any]. OpenAPI spec degrades to "object" for these endpoints.
**Pass:** Every handler declares a Pydantic BaseModel return type.
**Fail:** api/tasks.py:21 — returns `{"task_id": task.task_id, "status": task.status.value}`. health.py:16 — returns bare dict.
**Automated check available:** yes — mypy or AST check for dict return types on handlers

---

### API-002: All error responses must use a consistent error envelope
**Severity:** critical
**Rationale:** Errors are bare HTTPException with "detail" string only. Chat completions returns errors as 200 OK with error text in message body. No error code, request ID, or machine-readable type.
**Pass:** Global exception handler with ErrorResponse model (error, code, detail, request_id). Chat completions returns proper HTTP errors.
**Fail:** api/tasks.py:34 — `raise HTTPException(status_code=404, detail="Task not found")`. api/chat_completions.py:104 — `response_text = f"Error: {exc}"` returned as 200 OK.
**Automated check available:** partial — check for global exception handler registration

---

### API-003: WebSocket endpoint must authenticate before accepting connection
**Severity:** critical
**Rationale:** Every REST endpoint requires RequireAuth, but WebSocket at ws.py:22 unconditionally calls websocket.accept() with no auth. Task IDs are 12-char hex (48-bit entropy), making enumeration feasible.
**Pass:** Bearer token validated via query param or first message before accept(). websocket.close(code=4001) on failure.
**Fail:** api/ws.py:17-22 — accepts connection unconditionally, immediately streams task data.
**Automated check available:** yes — check ws.py for auth calls before accept()

---

### API-004: GitHub webhook must validate X-Hub-Signature-256
**Severity:** critical
**Rationale:** _verify_github_signature() defined but never called. Signature header is captured and discarded. Any POST triggers task creation.
**Pass:** Handler calls _verify_github_signature() with body, signature, and secret. Returns 403 on failure.
**Fail:** api/webhooks.py — _verify_github_signature at line 19 never called in handler body.
**Automated check available:** yes — grep for _verify_github_signature call in handler

---

### API-005: Redundant endpoints must be removed or differentiated
**Severity:** major
**Rationale:** GET /tasks/{task_id} and GET /tasks/{task_id}/result have identical implementations returning the same TaskResponse.
**Pass:** Remove /result endpoint, OR differentiate (return only TaskResult, add long-polling, etc.).
**Fail:** api/tasks.py:26-35 and :38-47 — identical logic returning same type.
**Automated check available:** yes — compare handler implementations

---

### API-006: GET /tasks must support cursor-based pagination
**Severity:** major
**Rationale:** Only accepts limit param, returns bare list. queue.list_tasks() does `list(self._tasks.values())[-limit:]` — unstable, O(n), no cursor or total count.
**Pass:** Accepts cursor + limit, returns PaginatedResponse with items, next_cursor, total.
**Fail:** api/tasks.py:62-68 — returns bare list with only limit. queue.py:83 — `list(self._tasks.values())[-limit:]`.
**Automated check available:** partial — check for cursor parameter on list endpoints

---

### API-007: Duplicated request-to-agent pipeline code must be extracted
**Severity:** major
**Rationale:** chat_completions.py contains two identical 7-line blocks (lines 91-104 and 143-156): user message extraction, TaskCreate construction, run_task call, exception handling. Bug fixes must be applied twice.
**Pass:** Single async function called by both streaming and non-streaming paths.
**Fail:** api/chat_completions.py:91-104 and :143-156 — near-identical code blocks.
**Automated check available:** partial — AST-based duplicate detection

---

### API-008: WebSocket message schemas must be defined as Pydantic models
**Severity:** minor
**Rationale:** WebSocket sends three distinct dict shapes via send_json with no schema definitions. Ad-hoc dicts cannot be validated, documented, or versioned.
**Pass:** WSProgressMessage, WSResultMessage, WSErrorMessage defined as Pydantic models.
**Fail:** api/ws.py:31, :39-45, :52-57 — inline dict construction.
**Automated check available:** yes — check for Pydantic model usage in ws.py send calls

---

### API-009: Health endpoint must use typed model and single version source
**Severity:** minor
**Rationale:** health.py:19 hardcodes "version": "0.1.0", main.py:51 also hardcodes version="0.1.0". Two literals that will drift. Returns dict[str, Any].
**Pass:** HealthResponse Pydantic model. Version from importlib.metadata or __version__ constant.
**Fail:** Two independent "0.1.0" string literals in health.py:19 and main.py:51.
**Automated check available:** yes — grep for hardcoded version strings

---

### API-010: MCP tools must return structured data, not human-formatted strings
**Severity:** major
**Rationale:** All 16 MCP tools return plain str. sandbox_exec returns `f"[exit {exit_code}]\n{output}"` — agents must parse strings. github_get_pr does `str(result)` on a dict.
**Pass:** Tools return dicts with explicit fields: `{"exit_code": int, "stdout": str, "success": bool}`.
**Fail:** tools/sandbox/server.py:41 — `f"[exit {exit_code}]\n{output}"`. tools/git/server.py:157 — `str(result)`.
**Automated check available:** partial — check MCP tool return type annotations

---

### API-011: POST /tasks must return full TaskResponse, not partial dict
**Severity:** major
**Rationale:** POST /tasks returns `{"task_id": str, "status": str}` — a two-field dict. GET returns full TaskResponse with 11 fields. Forces unnecessary round-trip for create-then-poll workflows.
**Pass:** POST returns full TaskResponse (202) with Location header.
**Fail:** api/tasks.py:23 — returns `{"task_id": task.task_id, "status": task.status.value}` discarding full TaskResponse.
**Automated check available:** yes — check POST handler return type

---

### API-012: Webhook endpoints must be protected and CI webhook must enforce a schema
**Severity:** critical
**Rationale:** Both webhooks lack auth entirely. CI webhook accepts raw request.json() with no schema — any JSON body with `{"status": "failure"}` triggers task creation.
**Pass:** CI webhook uses Pydantic model for request body. Both webhooks require auth (HMAC/shared secret).
**Fail:** api/webhooks.py:73-94 — raw request.json() with no schema, no auth, no signature.
**Automated check available:** yes — check webhook handler parameter types and auth dependencies

---

### CMPLX-001: Cyclomatic complexity must not exceed 10 per function
**Severity:** critical
**Rationale:** No function currently exceeds CC=10. Codifying prevents regression. Highest values: stream_task CC=8, check_permission CC=7.
**Pass:** Functions with at most 10 independent execution paths. Example: verify_api_key (CC=4).
**Fail:** Any function accumulating branches from multiple responsibilities that crosses CC=10.
**Automated check available:** yes — radon or ruff complexity checks

---

### CMPLX-002: Cognitive complexity must not exceed 15 per function
**Severity:** critical
**Rationale:** stream_task in ws.py reaches CogC~12 with `try > while > if > if > if` nesting. Limit of 15 prevents unreadable nested logic.
**Pass:** Functions with flat control flow using early returns. Example: verify_api_key uses early returns.
**Fail:** stream_task in api/ws.py:17-63 nests 4+ levels deep.
**Automated check available:** yes — cognitive-complexity linter (SonarQube, flake8-cognitive-complexity)

---

### CMPLX-003: Control flow nesting must not exceed 3 levels
**Severity:** major
**Rationale:** stream_task in ws.py requires holding 5 levels of mental context simultaneously. Extract inner logic into named functions.
**Pass:** _worker_loop in runner.py keeps `while > try > except` at exactly 3 levels, delegates to _execute_task.
**Fail:** api/ws.py:38-57 — `if > if > if` inside `while True` inside `try`, producing 5 nesting levels.
**Automated check available:** yes — AST-based nesting depth check

---

### CMPLX-004: Each function must have a single responsibility (max 2 distinct operations)
**Severity:** major
**Rationale:** _execute_task in runner.py performs 5+ responsibilities: task retrieval, status lifecycle (6 transitions), input construction, conductor invocation, result extraction.
**Pass:** Function delegates each concern. _transition_phases() handles status, _execute_task only orchestrates.
**Fail:** tasks/runner.py:49-104 — interleaves update_status, update_progress, TaskCreate construction, run_task, result extraction.
**Automated check available:** no — requires code review judgment

---

### CMPLX-005: No code block of 3+ substantive lines may be duplicated
**Severity:** major
**Rationale:** chat_completions.py has identical 7-line blocks at lines 91-104 and 143-156.
**Pass:** Shared logic extracted to a named function.
**Fail:** api/chat_completions.py:91-104 and :143-156 — near-identical user message extraction, task creation, conductor invocation, error formatting.
**Automated check available:** partial — duplicate code detection tools (jscpd, pylint duplicate-code)

---

### CMPLX-006: All numeric literals in business logic must be named constants
**Severity:** minor
**Rationale:** 11+ unexplained numbers: `chunk_size = 20` (chat_completions.py:107), `timeout=1.0` (runner.py:41), `0.5` (ws.py:60), `[:80]` (conductor.py:92,124), `[:500]` (webhooks.py:64, tracing.py:52), `50_000` (trust_boundary.py:51), `3600` (trust_boundary.py:33,120), `100000` (docker.py:103), `1536` (store.py:60).
**Pass:** `DESCRIPTION_LOG_PREVIEW_LEN = 80` defined at module level.
**Fail:** conductor.py:92 — `task.description[:80]` with no named constant.
**Automated check available:** partial — ruff/pylint magic number checks (with exceptions for 0, 1, -1)

---

### CMPLX-007: No os.environ.get() or I/O side effects at module import time
**Severity:** major
**Rationale:** config/models.py:33-60 calls os.environ.get() four times at import time. Values frozen at import, untestable without reload.
**Pass:** Environment values resolved lazily via functions or Settings.
**Fail:** config/models.py:33-60 — DEFAULT_TIERS evaluated at import time.
**Automated check available:** yes — AST check for os.environ at module level

---

### CMPLX-008: Functions must not mix abstraction levels
**Severity:** minor
**Rationale:** check_permission in trust_boundary.py mixes policy decisions with lazy `import re` on line 97. _get_tier_config packs null-check, enum validation, ternary, dictionary lookup into one expression.
**Pass:** Low-level concerns in helper functions. Policy function reads cleanly.
**Fail:** trust_boundary.py:97 — `import re` inside a permission policy function.
**Automated check available:** no — requires code review judgment

---

### CMPLX-009: Large declarative data structures (>10 entries) must be isolated from behavioral code
**Severity:** minor
**Rationale:** _DANGEROUS_COMMAND_PATTERNS (22 patterns) and _INJECTION_PATTERNS (27 patterns) dominate their modules, making behavioral code hard to review.
**Pass:** Pattern strings in a separate file (security/patterns.py or data file).
**Fail:** security/dangerous_tools.py:12-38 — 22 regex patterns inline with detection functions.
**Automated check available:** partial — line count heuristic for constant definitions

---

### CMPLX-010: Functions with more than 5 parameters must use a parameter object
**Severity:** minor
**Rationale:** Several functions approach the boundary. As Phase 2 adds complexity, parameter lists will grow. Existing pattern of Pydantic models for input (TaskCreate, ChatCompletionRequest) should be extended.
**Pass:** create_sandbox uses SandboxSettings to group 5 config values.
**Fail:** Hypothetical future function with 8+ positional parameters instead of using a settings model.
**Automated check available:** yes — AST check for function parameter count

---

### CMPLX-011: Consecutive status transition sequences (3+) must be extracted into named functions
**Severity:** major
**Rationale:** tasks/runner.py:54-104 has 6 consecutive update_status/update_progress calls with fake REVIEWING/TESTING phases. Phase transitions interleaved with business logic.
**Pass:** Extracted into _advance_through_phases(task_id, result).
**Fail:** runner.py:77-98 — six consecutive queue operations in main execution function.
**Automated check available:** partial — count consecutive update_status calls

---

### CMPLX-012: WebSocket streaming handlers must decompose poll-loop body into helpers
**Severity:** major
**Rationale:** stream_task in ws.py is the highest cognitive complexity function (CogC~12). Combines WebSocket lifecycle, polling, state-change detection, terminal detection, result serialization.
**Pass:** Extract _has_state_changed(), _build_update_message(), _is_terminal() as helpers.
**Fail:** ws.py:28-60 — while loop body with 5 nested conditionals and 3 interleaved responsibilities.
**Automated check available:** no — requires code review judgment

---

### PERF-001: Settings objects must be cached, never re-instantiated per call
**Severity:** critical
**Rationale:** get_settings() creates new Settings() on every invocation, re-parsing .env from disk and reconstructing 4 nested sub-objects. Called on every authenticated request via Depends().
**Pass:** `@functools.lru_cache() def get_settings() -> Settings: return Settings()`
**Fail:** config/settings.py:79-80 — `def get_settings() -> Settings: return Settings()` with no caching.
**Automated check available:** yes — check for lru_cache on get_settings

---

### PERF-002: Resource caches must have bounded size, TTL eviction, and shutdown cleanup
**Severity:** critical
**Rationale:** _containers dict in sandbox/server.py grows without bound. Each entry holds a live Docker container (512MB RAM). No TTL, max-size, or shutdown hook.
**Pass:** LRU eviction calling container.destroy(), OR periodic reaper, OR lifespan shutdown cleanup.
**Fail:** tools/sandbox/server.py:20 — `_containers: dict[str, SandboxContainer] = {}` with no eviction.
**Automated check available:** partial — check for unbounded dict caches of expensive resources

---

### PERF-003: Streaming endpoints must stream tokens incrementally from the LLM
**Severity:** critical
**Rationale:** _stream_conductor_response calls `await run_task(task)` to completion (10-60+ seconds), then chunks the completed string into 20-char pieces. Zero progress during LLM inference. Defeats streaming purpose.
**Pass:** Uses agent.run_stream() or equivalent async iterator yielding tokens as generated.
**Fail:** api/chat_completions.py:101-115 — `result = await run_task(task)` followed by string chunking loop.
**Automated check available:** partial — check for run_stream vs run usage in streaming paths

---

### PERF-004: Task runner must support configurable concurrent workers
**Severity:** critical
**Rationale:** Single _worker_loop processes one task at a time. Each task blocks 10-60+ seconds for LLM. 10 queued tasks = 10x wait. Head-of-line blocking under concurrent users.
**Pass:** TaskRunner accepts max_workers, spawns N concurrent asyncio.Tasks or uses Semaphore.
**Fail:** tasks/runner.py:38-47 — single asyncio.Task, sequential _execute_task.
**Automated check available:** partial — check TaskRunner.start() for multiple worker creation

---

### PERF-005: WebSocket progress must use event-driven notification, not polling
**Severity:** major
**Rationale:** ws.py polls every 0.5 seconds. Adds 500ms artificial latency. O(clients) lookups per interval regardless of state changes.
**Pass:** TaskQueue exposes asyncio.Event per task_id. update_status() signals it. WebSocket awaits it.
**Fail:** api/ws.py:60 — `await asyncio.sleep(0.5)` in polling loop.
**Automated check available:** yes — grep for asyncio.sleep in WebSocket handlers

---

### PERF-006: Stateless AI agent instances must be cached per model configuration
**Severity:** major
**Rationale:** run_task creates new Agent instance on every call via build_conductor(). Same (model, base_url) produces identical agent. Schema compilation and tool registration repeated unnecessarily.
**Pass:** build_conductor decorated with @lru_cache() or agents cached by (model, base_url) tuple.
**Fail:** agents/conductor.py:126 — `agent = build_conductor(model=resolved_model, base_url=base_url)` creating new Agent per task.
**Automated check available:** partial — check for caching on build_conductor

---

### PERF-007: LLM API calls must enforce configurable timeout
**Severity:** critical
**Rationale:** agent.run(prompt) at conductor.py:135 has no timeout. Hung LLM call blocks single-threaded runner forever. Chat completions also has no timeout.
**Pass:** `result = await asyncio.wait_for(agent.run(prompt), timeout=tier_config.timeout)` with per-tier timeouts.
**Fail:** conductor.py:135 — `result = await agent.run(prompt)` with no timeout wrapper.
**Automated check available:** yes — grep for agent.run without wait_for wrapper

---

### PERF-008: List operations on task store must not materialize full collection
**Severity:** major
**Rationale:** list_tasks() does `list(self._tasks.values())[-limit:]` — O(n) allocation every time. _tasks never prunes completed tasks. Grows without bound.
**Pass:** OrderedDict with max size, itertools.islice, or DB-backed storage.
**Fail:** tasks/queue.py:84 — `list(self._tasks.values())[-limit:]` with no pruning.
**Automated check available:** partial — check for list() wrapping of dict.values()

---

### PERF-009: Webhook endpoints must enforce request body size limits
**Severity:** major
**Rationale:** Both webhooks call request.json() on unbounded payloads. No Content-Length check, no middleware, no Pydantic validation. Multi-GB payload would be read into memory.
**Pass:** Use Pydantic model for request body, OR check Content-Length, OR configure body size middleware.
**Fail:** api/webhooks.py:34, :78 — `await request.json()` on raw Request with no limits.
**Automated check available:** yes — check webhook handlers for Pydantic model vs raw Request

---

### PERF-010: Configuration values read at import time must be lazy or refreshable
**Severity:** minor
**Rationale:** config/models.py:33-60 freezes MAISTRO_TIER_*_MODEL at import time. Cannot hot-swap models without restart. Inconsistent with conductor.py which reads LITELLM_BASE_URL per-task.
**Pass:** DEFAULT_TIERS computed by function, or values from Settings object.
**Fail:** config/models.py:33-60 — os.environ.get() at module level.
**Automated check available:** yes — grep for os.environ at module level outside config/settings.py

---

### PERF-011: Streaming error handlers must not silently embed errors in success responses
**Severity:** major
**Rationale:** chat_completions.py catches exceptions and returns `f"Error: {exc}"` as 200 OK content. Client cannot distinguish errors from completions. Stack trace destroyed.
**Pass:** Errors emitted as structured SSE error event or HTTPException. Original exception logged.
**Fail:** api/chat_completions.py:103-104 — `except Exception as exc: response_text = f"Error: {exc}"`.
**Automated check available:** partial — check for bare Exception catches in streaming generators

---

### PERF-012: Langfuse flush must not block the async event loop
**Severity:** major
**Rationale:** tracing.py:58 calls langfuse.flush() synchronously in async finally block. Blocks event loop for HTTP request duration. Adds latency to every traced call.
**Pass:** flush() via asyncio.to_thread(), or deferred to background task, or rely on SDK background flush.
**Fail:** observability/tracing.py:58 — `langfuse.flush()` synchronously in async function.
**Automated check available:** partial — check for synchronous flush calls in async functions

---

## Evaluation Protocol

When evaluating a file or pull request against these standards, follow these steps:

### Step 1: Identify Applicable Rules
- Determine which domain(s) the changed files fall into based on their path:
  - `api/` files: Apply all API-### and relevant ARCH-### rules
  - `agents/` files: Apply ARCH-###, COUP-###, PERF-006, PERF-007
  - `tasks/` files: Apply ARCH-###, COUP-###, PERF-004, PERF-008
  - `tools/` files: Apply ARCH-009, COUP-003, PERF-002
  - `security/` files: Apply CMPLX-### rules
  - `config/` files: Apply COUP-001, COUP-007, PERF-001, PERF-010
  - All files: Apply CMPLX-001 through CMPLX-006, TEST-### rules

### Step 2: Check Each Rule
For each applicable rule:
1. Read the **Pass criteria** — does the code meet it?
2. Read the **Fail criteria** — does the code match any failure pattern?
3. If the code matches a Fail pattern, record: `{RULE-ID}: {one-line description of violation}`

### Step 3: Classify Violations
- **Critical**: Must be fixed before merge. These represent security gaps, data loss risks, or fundamental design flaws.
- **Major**: Should be fixed before merge. These represent maintainability risks, performance issues, or API contract problems.
- **Minor**: Advisory. Can be addressed in a follow-up PR if the current change is otherwise sound.

### Step 4: Evaluate New Code
For new files or functions added in the PR:
- All CMPLX-### thresholds apply (complexity, nesting, duplication, magic numbers)
- If the new code introduces a module, check COUP-008 (must be imported by something)
- If the new code adds an endpoint, check API-001, API-002, API-003
- If the new code handles external input, check ARCH-001, ARCH-011

### Step 5: Check for Regressions
- Does the PR introduce new os.environ.get() calls outside config/? (COUP-001)
- Does the PR add new module-level mutable globals? (COUP-004)
- Does the PR add new inline/deferred imports? (COUP-006)
- Does the PR add new dict return types on endpoints? (API-001)
- Does the PR add new uncached expensive operations? (PERF-001, PERF-006)

### Step 6: Produce Report
Format the output as:

```
## Code Quality Review

### Critical Violations
- {RULE-ID}: {description} — {file:line}

### Major Violations
- {RULE-ID}: {description} — {file:line}

### Minor Violations
- {RULE-ID}: {description} — {file:line}

### Summary
{n} critical, {m} major, {p} minor violations found.
Recommendation: BLOCK / APPROVE WITH CHANGES / APPROVE
```

---

## Waiver Process

Some rule violations may be intentional and justified. When Claude encounters a potential waiver:

### 1. Identify the Waiver Candidate
A violation is a waiver candidate if:
- The code includes a comment like `# WAIVER: ARCH-001 — reason`
- The violation is in test code (test files may violate production rules where necessary)
- The code is in a migration or one-time script
- The violation is a conscious Phase 1 trade-off documented in a docstring

### 2. Validate the Waiver
A waiver is valid if:
- The comment explicitly names the rule ID being waived
- The reason is specific and technical (not "we'll fix it later" without a tracked issue)
- The waiver scope is narrow (one function/one file, not an entire module)
- For Phase 1 trade-offs: the docstring mentions the specific phase and planned resolution

### 3. Report Waived Violations
Still report the violation, but mark it:
```
- {RULE-ID} (WAIVED): {description} — {file:line} — Waiver: {reason}
```

### 4. Invalid Waivers
Flag these as violations despite the waiver comment:
- Critical security rules (ARCH-001, ARCH-005, ARCH-011, API-003, API-004) cannot be waived
- Performance rules that affect availability (PERF-003, PERF-004, PERF-007) cannot be waived without an alternative mitigation documented in the waiver
- Waivers that say "TODO" or "fix later" without a linked issue number are not valid
