# Competitive Improvements: Hermes / Pi / OpenClaw Analysis

**Date:** 2026-05-19
**Sources:** NousResearch/hermes-agent (2,700+ commits/month), earendil-works/pi (~50 commits/month), openclaw/openclaw (~50 commits/month)
**Purpose:** Identify actionable techniques from three leading agent frameworks, deduplicate overlaps, and produce a prioritized implementation plan for maistro-engine.

---

## Methodology

Deep source-code analysis of all three repositories (not just commit messages). Techniques were extracted across 12 dimensions: agent architecture, self-improvement, tool systems, session management, error handling, model management, security, configuration, observability, infrastructure, testing, and extensibility. 184 raw techniques were identified, then merged into 90 deduped items where overlaps between repos indicate the strongest signals.

### Source Legend

| Code | Repository | Stars | Focus |
|------|-----------|-------|-------|
| **H** | NousResearch/hermes-agent | ~25k | Full-stack agent gateway with 10+ platform adapters |
| **P** | earendil-works/pi | ~50k | Coding agent framework (3-layer TypeScript monorepo) |
| **OC** | openclaw/openclaw | ~125k | Agent platform with ACP, Codex runtime, plugin system |

### Impact Tier Definitions

| Tier | Label | Criteria |
|------|-------|----------|
| **P0** | Critical | System is fragile or broken without this. Blocks production use. |
| **P1** | High | Major quality, reliability, or productivity gain. Should be in next sprint. |
| **P2** | Medium | Important polish or architectural improvement. Plan for near-term. |
| **P3** | Low | Nice-to-have. Ship when convenient or when touching related code. |

### Difficulty Definitions

| Difficulty | Meaning |
|-----------|---------|
| **add-only** | New file/module, no existing code changes |
| **minor-change** | Small edits to existing code, <50 LOC touched |
| **refactor** | Restructuring existing code, behavior preserved |
| **major-change** | Cross-cutting changes affecting multiple modules |

---

## Overlap Map

Techniques found in 2-3 repos are the strongest adoption signals — they represent convergent evolution toward industry-standard patterns.

| Technique | H | P | OC | Signal Strength |
|-----------|---|---|----|----------------|
| Error classification pipeline | Y | Y | Y | 3/3 — universal |
| Lazy dependency loading | Y | Y | Y | 3/3 — universal |
| Before/after execution hooks | Y | Y | Y | 3/3 — universal |
| Plugin/extension system | Y | Y | Y | 3/3 — universal |
| Steering / mid-run guidance | Y | Y | Y | 3/3 — universal |
| Config hot reload / live config | Y | Y | Y | 3/3 — universal |
| Session persistence (structured) | Y | Y | Y | 3/3 — universal |
| Fallback chains | Y | Y | Y | 3/3 — universal |
| Credential pool / key rotation | Y | - | Y | 2/3 — infra-heavy |
| Context compaction | Y | Y | - | 2/3 — agent core |
| Session branching / tree history | Y | Y | - | 2/3 — session mgmt |
| Secret redaction | Y | - | Y | 2/3 — security |
| Phase machine / lifecycle states | - | Y | Y | 2/3 — execution |
| Schema sanitization | Y | - | Y | 2/3 — tool compat |
| Message sanitization | Y | Y | - | 2/3 — LLM compat |
| Guardrails / circuit breakers | Y | - | Y | 2/3 — resilience |
| Jittered backoff | Y | - | Y | 2/3 — resilience |
| Per-provider timeout | Y | - | Y | 2/3 — reliability |
| File mutation tracking | Y | Y | - | 2/3 — correctness |
| Orphaned state recovery | Y | - | Y | 2/3 — crash safety |
| Delivery queue / backpressure | Y | - | Y | 2/3 — flow control |
| Two-phase commit | - | Y | Y | 2/3 — atomicity |
| KV cache / prompt stability | Y | Y | - | 2/3 — performance |
| Cost tracking | Y | Y | - | 2/3 — economics |
| Structured logging | Y | - | Y | 2/3 — observability |
| Docker hardening | Y | - | Y | 2/3 — deployment |
| Health diagnostics | Y | - | Y | 2/3 — operations |

---

## Category 1: Error Handling & Resilience

### IMP-001: Priority-ordered error classification pipeline

**Sources:** H + P + OC (3/3)
**Impact:** P0 Critical
**Difficulty:** add-only

**Plan:**
Create `maistro/resilience/classifier.py` implementing an ordered pipeline of error classifiers. Each stage returns a `ClassifiedError` with `retryable`, `should_fallback`, `should_rotate_credential`, `severity` flags. Stages run in priority order: provider-specific patterns, HTTP status + message, error codes, message regex, SSL/TLS transient, server disconnect + size inference, transport heuristics, unknown fallback.

**Purpose:**
Replace our current ad-hoc `try/except` blocks with a single, deterministic error classification system. Every error that flows through the graph executor, benchmark harness, or API router gets classified the same way.

**Why important overall:**
All three frameworks independently converged on this pattern. Without it, errors are handled inconsistently — some paths retry, some fail silently, some crash. Classified errors enable automated recovery decisions.

**Why important for maistro:**
Our benchmark harness calls 8 different LLM providers. Each fails differently. Currently we catch generic `Exception` and have no recovery strategy. This is the single highest-impact improvement for evaluation reliability.

**Why better than current:**
We have no error classification at all — just bare `try/except Exception` in benchmark runners. Errors silently fail evaluations, producing garbage fitness scores. Classified errors let us distinguish "transient rate limit, retry in 5s" from "billing exhausted, stop this provider" from "model produced bad JSON, score 0".

**Why better than alternatives:**
A simple `is_transient(error)` boolean function misses the nuance. The pipeline approach lets us add provider-specific stages (e.g., "Anthropic overloaded" vs "OpenAI context overflow") without touching core logic. Pi's simpler `isTransientProviderOperationError()` works for one provider but doesn't scale to 8.

---

### IMP-002: Transient vs permanent error disambiguation

**Sources:** H + OC (2/3)
**Impact:** P0 Critical
**Difficulty:** minor-change (depends on IMP-001)

**Plan:**
Within the error classifier, implement specific disambiguators: (1) HTTP 402 split into billing-exhausted (permanent) vs usage-limit-transient (retryable), (2) HTTP 403 split into entitlement-denied (permanent) vs tier-upgrade (informational), (3) server disconnect with large session inferred as context overflow (trigger compression), (4) SSL/TLS alerts as transient transport errors.

**Purpose:**
Not all errors are equal. A 429 "try again in 60s" is recoverable. A 402 "insufficient credits" is not. A silent disconnect on a 100k-token request is context overflow, not a network glitch.

**Why important overall:**
Misclassifying a permanent error as transient causes infinite retry loops. Misclassifying a transient error as permanent wastes time and money. The 402 billing-vs-transient split alone saves significant cost in production.

**Why important for maistro:**
During evolution cycles, we run hundreds of evaluations against paid APIs. A transient rate limit should pause and retry. A billing exhaustion should rotate to the next credential. Currently we treat both the same (fail or retry blindly).

**Why better than current:**
No disambiguation exists. Every HTTP error is either retried or not, with no nuance.

**Why better than alternatives:**
Simply checking `status_code >= 500` misses that 402 can be transient (usage limits) and 429 needs backoff coordination. Hermes's `_classify_402()` is the most thorough implementation.

---

### IMP-003: Jittered exponential backoff with configurable ceiling

**Sources:** H + OC (2/3)
**Impact:** P0 Critical
**Difficulty:** add-only

**Plan:**
Create `maistro/resilience/backoff.py` with `jittered_backoff(attempt, base=1.0, max_delay=60.0)` returning `base * 2^(attempt-1) * random(0.5, 1.0)` capped at `max_delay`. Add `max_retry_delay_ms` parameter to all provider call sites. If server requests delay exceeding cap, fail immediately with the delay exposed.

**Purpose:**
Prevent thundering herd after provider outages. Allow callers to configure ceiling per operation (benchmark eval = 30s max, production DAG = 120s max).

**Why important overall:**
Without jitter, all concurrent requests retry at the same instant, amplifying the outage. Without a ceiling, a provider requesting "retry in 3600s" blocks the entire evolution cycle.

**Why important for maistro:**
Our evolution cycle runs batch evaluations. When a provider goes down, 50+ concurrent evaluations all retry simultaneously, making the outage worse. Jittered backoff staggers recovery.

**Why better than current:**
We use `asyncio.sleep(2)` hardcoded in a few places. No jitter, no ceiling, no configurability.

**Why better than alternatives:**
Tenacity/decorator-based retry libraries add complexity and hide control flow. A simple function that returns a delay is explicit, testable, and composable. Both Hermes and OpenClaw converged on this approach independently.

---

### IMP-004: Context-overflow inference from silent failures

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
In the graph executor, when a node's LLM call fails with `RemoteProtocolError` or empty response, check if the request exceeded 60% of the model's context window or 200+ messages. If so, classify as context overflow and trigger compression instead of retry.

**Why important overall:**
Providers silently drop oversized requests without returning a proper error code. Without this inference, the system retries the same oversized request indefinitely.

**Why important for maistro:**
Long-running DAGs accumulate context. A node processing a large accumulated blackboard can silently fail. Currently we'd retry the same oversized context forever.

**Why better than current:**
No context overflow detection. Silent failures are treated as transient network errors.

**Why better than alternatives:**
The alternative (proactively counting tokens before every call) adds latency to every request. Hermes's heuristic (check only on failure, correlate with session size) is zero-cost on the happy path.

---

### IMP-005: Anti-thrashing guard for compression loops

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Track the savings percentage of the last two compression operations. If both saved less than 10%, disable further compression and surface a warning directing the user to start a new context or provide a manual summary. Reset the guard on new user input.

**Why important overall:**
Without this guard, compression can enter an infinite loop where each pass removes 1-2 messages, immediately hits the limit again, and compresses again — burning tokens with no progress.

**Why important for maistro:**
Evolution fitness evaluation contexts grow as benchmark results accumulate. Without the guard, a stuck evaluation burns through API credits.

**Why better than current:**
No anti-thrash protection. A compression loop would run until timeout or credit exhaustion.

**Why better than alternatives:**
A simple max-compression-count is too rigid (some contexts need 3-4 compressions legitimately). The savings-ratio heuristic is adaptive — it only triggers when compression is actually ineffective.

---

### IMP-006: Grace window for deferred terminal error cleanup

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
When a node execution encounters a transient error during provider retry (SSL reset, timeout), defer marking the node as failed for 15 seconds. If a subsequent retry succeeds within the window, cancel the failure. Only finalize failure after the grace period expires.

**Why important overall:**
Provider APIs emit transient error events mid-retry that look like terminal failures but resolve within seconds. Without the grace window, these cause false-positive failure announcements that cascade through the system.

**Why important for maistro:**
During tournament battles, two genomes are evaluated head-to-head. A false-positive failure on one genome produces a misleading Elo change, poisoning the tournament rankings.

**Why better than current:**
Errors are immediately terminal. No grace period or deferred cleanup.

**Why better than alternatives:**
Simply retrying 3 times with fixed delays is less effective than a grace-window approach because the retry count can be exhausted by transient blips that would have self-resolved.

---

### IMP-007: Dead connection cleanup before each turn

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Before each LLM API call in the graph executor, detect and remove stale TCP connections from the httpx client's connection pool. A connection is stale if the remote end closed it (half-open state).

**Why important overall:**
After provider outages or network interruptions, httpx connection pools retain zombie sockets. The next API call hangs on a dead connection for up to the timeout duration, adding 30-120s of latency to every request until the pool refreshes.

**Why important for maistro:**
Benchmark evaluations are time-sensitive. A dead connection adds 120s to a single evaluation. With 8 benchmarks × 111 test samples × 50 population size, dead connections can add hours to an evolution cycle.

**Why better than current:**
No connection pool management. We create a new httpx client per request in most places (which is wasteful) or hold a long-lived client (which accumulates dead connections).

**Why better than alternatives:**
Setting a low `pool_idle_timeout` on httpx clients is blunt — it closes healthy connections too. Hermes's approach of proactively cleaning only dead connections before each call is more targeted.

---

### IMP-008: Cross-process rate limit coordination

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Implement a shared rate-limit state file (or SQLite table) that all concurrent processes (graph executor, benchmark runners, evolution cycle) check before making API calls. When one process hits a rate limit, it writes the reset time. Other processes read it and skip their call if reset time hasn't passed.

**Why important overall:**
Multiple processes sharing the same API key amplify rate limits. Each process independently hitting the rate limit deepens the hole (each attempt counts against RPH). Coordination prevents this.

**Why important for maistro:**
Our evolution cycle runs multiple benchmarks concurrently, all using the same LiteLLM proxy. Without coordination, parallel evaluations trip rate limits that cascade into failures.

**Why better than current:**
No coordination. Each benchmark runner independently retries on rate limits, making the problem worse.

**Why better than alternatives:**
A centralized rate-limiter service adds operational complexity. A shared state file (like Hermes's approach) is zero-infrastructure and works across processes on the same host.

---

### IMP-009: Stage-aware retry policies

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Define retry policies per operation stage: `read` operations (model listing, health checks) get aggressive retry (3 attempts, 250ms base); `evaluate` operations (benchmark scoring) get moderate retry (2 attempts, 1s base); `write` operations (posting results, updating fitness) get no retry by default since they may not be idempotent.

**Why important overall:**
Retrying a read is safe and cheap. Retrying a write may duplicate data. Retrying an evaluation needs balance (you want reliability but can't spend unlimited time). One-size-fits-all retry is suboptimal.

**Why important for maistro:**
Our benchmark harness treats all operations the same — it retries everything or nothing. Stage-aware policies let us be aggressive on reads (model listing), moderate on evaluations (benchmark scoring), and conservative on writes (fitness updates).

**Why better than current:**
Single retry policy applied to all operations regardless of idempotency or cost.

**Why better than alternatives:**
Per-provider retry (Hermes) misses that the same provider needs different policies for different operations. Per-stage (OpenClaw) is the right granularity.

---

### IMP-010: Graceful degradation with guaranteed completion events

**Sources:** P (novel)
**Impact:** P0 Critical
**Difficulty:** refactor

**Plan:**
Enforce a contract on all graph executor node runs: the execution must always emit a completion event (success or failure), never throw an unhandled exception. On unhandled errors, synthesize a failure result with `stopReason: "error"` and `errorMessage`. This guarantees that DAG execution state machines always transition, never hang.

**Why important overall:**
If a node throws an unhandled exception, the DAG executor's state machine gets stuck in "running" forever. There is no timeout that can rescue it if the event loop is blocked. Guaranteed completion events prevent this.

**Why important for maistro:**
Our graph executor has no such guarantee. A malformed LLM response or unexpected tool output can throw inside a node, leaving the DAG in a permanent "running" state with no way to recover except manual intervention.

**Why better than current:**
Exceptions from nodes propagate up and crash the DAG executor. No synthetic failure result. No guaranteed state transition.

**Why better than alternatives:**
Wrapping each node in a timeout helps but doesn't address all failure modes (e.g., exceptions during result processing after the timeout fires). Pi's approach of encoding failures in the stream is more robust — the stream contract itself guarantees termination.

---

## Category 2: Model Management & Credentials

### IMP-011: Multi-credential pool with strategy-based selection

**Sources:** H + OC (2/3)
**Impact:** P0 Critical
**Difficulty:** add-only

**Plan:**
Create `maistro/credentials/pool.py` implementing `CredentialPool` with four selection strategies: `fill_first` (use highest priority until exhausted), `round_robin`, `random`, and `least_used`. Each credential tracks `last_status`, `last_error_code`, `cooldown_until`. Configure strategy per provider in `config.yaml`.

**Purpose:**
Support multiple API keys per provider. When one key hits a rate limit or billing exhaustion, automatically rotate to the next. Different strategies optimize for different goals (cost spreading vs. simplicity).

**Why important overall:**
Production systems need key rotation. A single key is a single point of failure. Both Hermes and OpenClaw independently built credential pools, confirming this is table-stakes infrastructure.

**Why important for maistro:**
Our evolution engine evaluates hundreds of genomes against paid APIs. A single API key limits throughput and risks rate limits. With a pool, we can use multiple keys to parallelize evaluations and continue operating when one key is exhausted.

**Why better than current:**
Single API key per provider, configured via environment variable. No rotation, no fallback, no tracking.

**Why better than alternatives:**
LiteLLM has basic key rotation but no strategy selection, no cooldown tracking, and no integration with our error classifier. Building our own pool gives us full control over rotation logic and integrates with IMP-001 error classification.

---

### IMP-012: API key rotation with automatic cycling

**Sources:** OC + H (2/3)
**Impact:** P0 Critical
**Difficulty:** add-only (depends on IMP-011)

**Plan:**
On rate-limit errors (429) or billing errors (402), the credential pool automatically cycles to the next available key. Inner loop retries the same key with backoff for transient failures. Outer loop rotates keys for rate-limit failures. If all keys exhausted, propagate a "pool exhausted" error with `soonest_available_at` timestamp.

**Why important overall:**
Key rotation without automatic cycling is manual — someone has to notice a key is exhausted and switch. Automatic cycling means the system self-heals.

**Why important for maistro:**
During overnight evolution runs, a key hitting a rate limit at 3AM shouldn't halt the entire cycle. Automatic rotation to the next key keeps the run going.

**Why better than current:**
No rotation. When a key hits rate limit, the operation fails and the evolution cycle stalls.

**Why better than alternatives:**
LiteLLM's built-in rotation doesn't track per-key cooldown periods or distinguish billing exhaustion from rate limits. Our rotation integrates with IMP-001 classification to make smarter decisions.

---

### IMP-013: Fallback chain with ordered providers and primary restore

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Define `_fallback_chain` as an ordered list of `{provider, model, api_key, base_url}` per graph node config. When primary fails (rate-limit, overload, connection), activate first fallback. After a successful turn with fallback, attempt primary restoration on the next turn. Track fallback state per-node in the DAG blackboard.

**Why important overall:**
Multi-provider fallback is essential for production reliability. But permanently staying on a fallback wastes money if the primary recovers. The primary-restore pattern ensures optimal cost once the primary is back.

**Why important for maistro:**
Our graph executor has no fallback mechanism. A single provider outage crashes the entire DAG execution. With fallback chains, each node can degrade gracefully (e.g., GPT-4 → Claude → Gemini) and automatically recover when the preferred provider returns.

**Why better than current:**
No fallback. Single provider per node. Provider outage = execution failure.

**Why better than alternatives:**
Round-robin across providers (LiteLLM's routing) spreads load but doesn't have the concept of "preferred primary with temporary fallback." The ordered chain + restore pattern is more appropriate for our use case where we want to optimize for quality first and fall back only when necessary.

---

### IMP-014: Cross-process OAuth token synchronization

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
When using OAuth-based providers (xAI, Nous, Azure), detect if another process has refreshed the token (by checking file mtime on `auth.json`). If the in-memory token is stale, sync from disk before attempting the API call. Prevents "refresh_token_reused" errors when multiple processes share the same OAuth app.

**Why important overall:**
OAuth refresh tokens are often single-use. If two processes both try to refresh simultaneously, one gets a "token already used" error. Cross-process sync prevents this race.

**Why important for maistro:**
Multiple benchmark runners may share the same OAuth-credentialed provider. Without sync, token refresh races cause cascading auth failures.

**Why better than current:**
No OAuth token management. Each process independently uses whatever token is in the environment.

**Why better than alternatives:**
A centralized token service adds operational complexity. File-based sync (Hermes's approach) is simple and works for single-host deployments.

---

### IMP-015: Automatic API mode detection

**Sources:** H (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Auto-detect whether to use `chat_completions`, `anthropic_messages`, `bedrock_converse`, or `codex_responses` based on provider name, base URL hostname, and model name patterns. Store the detected mode on the client instance. Allow manual override via config.

**Why important overall:**
Different providers require different API formats. Hardcoding the mode per-provider is fragile (new providers, new models). Auto-detection adapts automatically.

**Why important for maistro:**
Our benchmark runners currently hardcode `chat_completions` for all providers. Anthropic and Bedrock models get wrong-format requests that fail silently or produce garbage.

**Why better than current:**
Single API format assumed for all providers. Anthropic models fail with cryptic errors.

**Why better than alternatives:**
Requiring users to specify `api_mode` in config for every provider is error-prone. Auto-detection from URL/model patterns follows the convention-over-configuration principle.

---

### IMP-016: Context length probing with tiered fallback

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
When a model's context length is unknown, probe with progressively larger request sizes (4k → 16k → 64k → 128k → 200k). On context-overflow error, parse the actual limit from the error message and cache it in the model registry. Use the cached value for all subsequent requests to that model.

**Why important overall:**
Many local and custom models don't report context length via API. Without knowing the limit, you can't manage context or prevent overflow errors.

**Why important for maistro:**
Our graph executor needs to know context length to decide when to compress. For local Ollama models, this info isn't always available. Probing + caching solves it once per model.

**Why better than current:**
Hardcoded context lengths or None (no management). Models without metadata get no context management.

**Why better than alternatives:**
Simply trying the maximum and hoping it works wastes tokens on overflow errors. The tiered probe minimizes waste by starting small.

---

### IMP-017: Provider-specific header injection

**Sources:** H (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Define a header registry mapping base_url hostname patterns to required headers (OpenRouter: user-agent, NVIDIA NIM: billing-origin, GitHub Copilot: editor-version). Inject headers at httpx client construction time based on URL match.

**Why important overall:**
Different providers require different headers for auth, billing, or rate-limit tracking. Missing headers cause silent failures or wrong billing attribution.

**Why important for maistro:**
Our conductor-router already routes to multiple providers. Adding header injection ensures each provider gets the right headers without modifying every call site.

**Why better than current:**
No provider-specific headers. Some providers reject requests or apply wrong billing.

**Why better than alternatives:**
Passing headers manually at every call site is error-prone. Centralized injection at client construction is set-and-forget.

---

### IMP-018: Auth profile system with cooldown and failure tracking

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Extend the credential pool (IMP-011) with auth profiles that track per-profile state: `status` (active/cooldown/blocked), `cooldown_until`, `failure_count`, `last_failure_at`. `markAuthProfileFailure()` transitions to cooldown with configurable duration (5min for 401, 1hr for 429/billing). `getSoonestCooldownExpiry()` tells callers when the next profile becomes available.

**Why important overall:**
A failed credential shouldn't be retried immediately — it amplifies the rate limit or wastes time on a known-bad key. Cooldown tracking prevents this.

**Why important for maistro:**
During tournament battles, we evaluate pairs of genomes concurrently. A failed credential shouldn't be retried by the second genome's evaluation — it should wait for cooldown or rotate.

**Why better than current:**
No failure tracking. Failed keys are retried immediately, compounding the problem.

**Why better than alternatives:**
Simple cooldown (Hermes) works but doesn't track failure count or type. OpenClaw's profile system with typed cooldown durations (401 vs 429 vs billing) is more nuanced and prevents wasted attempts.

---

### IMP-019: External CLI auth discovery

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Scan for existing CLI tool credentials (Claude CLI `~/.claude/.credentials.json`, Codex CLI auth store, Ollama local keys) and automatically register them as auth profiles. Discovery runs once at startup and results are cached.

**Why important overall:**
Users often have API keys configured in other tools. Requiring separate configuration for every tool is friction. Auto-discovery reduces setup time.

**Why important for maistro:**
Our dev server already has credentials in `~/.conductor-secrets/conductor.env` and LiteLLM config. Auto-discovery would let the benchmark harness find and use these without duplicate configuration.

**Why better than current:**
Credentials must be manually configured in every service. No cross-service discovery.

**Why better than alternatives:**
A shared credentials file (like AWS `~/.aws/credentials`) is a convention that requires adoption. Auto-discovery from existing tools meets users where they are.

---

### IMP-020: OAuth token proactive refresh

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Before each API call using an OAuth credential, check if the token expires within the next 60 seconds. If so, proactively refresh it before making the call. This prevents mid-request auth failures that waste the entire request (including token costs for the failed prompt).

**Why important overall:**
OAuth tokens expire. A mid-request 401 wastes the prompt tokens already sent ( Anthropic charges for the input even on auth failure). Proactive refresh eliminates this waste.

**Why important for maistro:**
Evolution evaluations are expensive. An auth failure mid-evaluation wastes the prompt tokens for that entire benchmark run. Proactive refresh prevents this.

**Why better than current:**
Tokens are used until they fail. No proactive refresh. Failed requests waste tokens.

**Why better than alternatives:**
Refreshing on a fixed schedule (every 55 minutes) is wasteful if the token isn't being used. Proactive refresh (check before use) is more efficient.

## Category 3: Graph Execution Architecture

### IMP-021: IterationBudget shared across parent + subgraphs

**Sources:** H + OC (2/3)
**Impact:** P0 Critical
**Difficulty:** add-only

**Plan:**
Create `IterationBudget(max_iterations)` as a mutable counter. The DAG executor creates one per top-level run and passes it to every node. Subgraph invocations inherit the same counter. Every LLM turn (in any node or subgraph) decrements the counter. On exhaustion, the grace call mechanism (IMP-022) fires.

**Purpose:**
Prevent total iteration explosion when a DAG spawns subgraphs that spawn subgraphs. Without shared budget, each subgraph independently consumes its full allocation, leading to unbounded iteration.

**Why important overall:**
Both Hermes (delegation budget) and OpenClaw (hierarchical depth limits) independently solved this. It is the primary defense against runaway agent loops.

**Why important for maistro:**
Our graph executor currently has per-node retry limits but no global budget. A DAG with 10 parallel nodes each retrying 3 times = 30 iterations minimum. With subgraphs, this explodes combinatorially. A shared budget caps total work.

**Why better than current:**
Per-node retry limits only. No cross-node or cross-subgraph budget. Runaway DAGs consume unlimited API credits.

**Why better than alternatives:**
Max-depth limits (OpenClaw) prevent infinite nesting but don't cap total iterations. A shared iteration budget is more direct — it limits the actual work done, regardless of topology.

---

### IMP-022: Phase machine for operation lifecycle

**Sources:** P + OC (2/3)
**Impact:** P0 Critical
**Difficulty:** refactor

**Plan:**
Replace the graph executor's ad-hoc state tracking with a formal phase machine. Phases: `idle | running | paused | compressing | failing | completed | failed`. Operations like `run()`, `pause()`, `compress()` check current phase and throw `ExecutorBusyError` if the phase doesn't allow the operation. Phase transitions are logged and emitted as events.

**Purpose:**
Prevent concurrent mutations of executor state. A DAG can't be paused while already paused, can't be run while compressing, can't be run while already running. The phase machine makes these invariants explicit and enforced.

**Why important overall:**
Both Pi (AgentHarness phase) and OpenClaw (lifecycle phases) converged on this. It prevents a whole class of race conditions in concurrent agent systems.

**Why important for maistro:**
Our graph executor has a `status` field but no enforcement. A WebSocket client can trigger `run` while the DAG is already running, creating two concurrent execution loops that corrupt the blackboard.

**Why better than current:**
Status field is informational, not enforced. Operations don't check state before executing. Race conditions are possible.

**Why better than alternatives:**
A full state machine library (like `transitions` or `python-statemachine`) adds a dependency for marginal benefit. A simple phase enum with guard checks (Pi's approach) is sufficient and dependency-free.

---

### IMP-023: Hierarchical depth and role system for subgraphs

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Assign roles based on subgraph depth: depth 0 = root (can spawn subgraphs), depth 1..max-1 = orchestrator (can spawn children), depth == max = leaf (terminal, cannot spawn). The role determines `controlScope` and `canSpawn`. Enforce at the subgraph invocation boundary.

**Why important overall:**
Without depth limits, a recursive DAG can create infinite subgraphs. The role system provides a bounded tree with guaranteed terminal nodes.

**Why important for maistro:**
Our graph executor supports subgraph nodes but has no depth limit. A DAG that references itself creates infinite recursion. The depth + role system prevents this with a compile-time check.

**Why better than current:**
No depth limit on subgraph nesting. Infinite recursion is possible. No role distinction between spawning and terminal nodes.

**Why better than alternatives:**
A simple max-depth counter prevents nesting but doesn't distinguish roles. OpenClaw's role system (main/orchestrator/leaf) gives each depth level different capabilities, which is useful for our tournament where orchestrator nodes should be able to spawn but leaf evaluation nodes should not.

---

### IMP-024: Event sink pattern for declarative execution

**Sources:** P + H (2/3)
**Impact:** P1 High
**Difficulty:** refactor

**Plan:**
Define `GraphEventSink` protocol with typed callbacks: `on_node_start`, `on_node_complete`, `on_node_error`, `on_subgraph_spawn`, `on_subgraph_complete`, `on_dag_complete`, `on_dag_failed`. The graph executor calls these instead of mixing UI/persistence logic into the execution loop. Callers (WebSocket handler, API handler, test harness) subscribe to events they care about.

**Why important overall:**
Separates execution logic from presentation/persistence. Pi's `AgentEventSink` and Hermes's stream event system both use this pattern. It makes the executor testable without mocking HTTP servers.

**Why important for maistro:**
Our graph executor currently mixes execution, logging, WebSocket streaming, and state persistence into a single `run()` method. This makes it impossible to test execution without a WebSocket server and makes adding new consumers (e.g., tournament battle observer) require modifying the executor.

**Why better than current:**
Execution logic tangled with WebSocket streaming and state persistence. Adding a new consumer requires modifying the executor.

**Why better than alternatives:**
A callback function per event type (current approach) works but isn't typed. The event sink protocol provides type safety and makes the contract explicit. Subscribers can be composed (WebSocket sink + logging sink + metrics sink).

---

### IMP-025: Steering / mid-run guidance without interruption

**Sources:** H + P + OC (3/3)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Implement `steer(guidance: str)` on the graph executor that appends guidance to the current node's context without triggering a restart or interrupt. The guidance appears in the next LLM call's tool result message, preserving role alternation. A steering queue accumulates messages between node completions and drains before the next node starts.

**Why important overall:**
All three frameworks independently built steering mechanisms. Users need to provide mid-run guidance ("focus on accuracy, not speed") without restarting the entire execution. Steering is distinct from interruption.

**Why important for maistro:**
During long DAG runs, users should be able to provide course corrections via the WebSocket UI. Currently, the only option is to cancel and restart. Steering lets them adjust mid-run.

**Why better than current:**
No mid-run guidance. The only option is cancel + restart with modified config.

**Why better than alternatives:**
Hermes's approach (append to tool result) is simpler than Pi's (queue + drain) and doesn't break message flow. OpenClaw's steer-restart creates a new run, which is heavier. We'll use Hermes's append pattern for simplicity.

---

### IMP-026: Orphaned execution detection and reconciliation

**Sources:** OC + H (2/3)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Persist DAG execution state to disk/SQLite. On startup, `restoreExecutions()` loads persisted state and identifies orphaned runs (status=running but no live executor). For each orphan, check if completion evidence exists in the execution log. If found, finalize post-hoc. If not, mark as failed and log diagnostics.

**Why important overall:**
Process crashes leave executions in "running" state forever. Without reconciliation, these zombie executions accumulate and confuse the UI and API.

**Why important for maistro:**
If the hive-conductor crashes during an evolution cycle, all in-progress DAG runs become zombies. On restart, they show as "running" but never complete. Reconciliation cleans these up automatically.

**Why better than current:**
No crash recovery. In-memory state is lost on restart. Zombie executions persist until manually cleared.

**Why better than alternatives:**
Simply marking all "running" executions as failed on restart loses legitimate completions that happened just before the crash. OpenClaw's approach of checking the execution log for evidence first is more accurate.

---

### IMP-027: Stale active run detection with grace period

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
A background sweeper (30s interval) checks for executions that have been "running" for longer than their expected duration + grace period (60s). If the executor has no live context, mark the execution as stale. Check execution log for completion evidence before finalizing. Emit a diagnostic event with the stale duration.

**Why important overall:**
Even without a full crash, executions can become stale (deadlock, zombie thread, lost network connection). The sweeper provides a safety net.

**Why important for maistro:**
Long-running benchmark evaluations can hang on provider timeouts or deadlocks. The sweeper detects these and frees up the evolution cycle to continue with other genomes.

**Why better than current:**
No staleness detection. Hung executions block forever.

**Why better than alternatives:**
A per-execution timeout is blunter — it kills legitimate long-running evaluations. The grace period approach (expected duration + buffer) is more adaptive.

---

### IMP-028: Suspended delivery queue with backpressure

**Sources:** OC + H (2/3)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
When a node completes but the parent node is unavailable (e.g., another parallel node is still running), queue the completion for later delivery. Queue has soft cap (25 items), hard cap (50 items), and pressure target (10 items). When hard cap exceeded, prune oldest deliveries. Different expiry times by source (cron: 2hr, subgraph: 6hr, interactive: 24hr).

**Why important overall:**
In a parallel DAG, nodes complete at different speeds. Without a delivery queue, fast completions are lost if the consumer isn't ready.

**Why important for maistro:**
Our graph executor's parallel node completion handlers currently assume the parent is always ready. In complex DAGs with fan-in nodes, completions can be lost if the fan-in hasn't started yet.

**Why better than current:**
No queuing. Completions delivered immediately to parent. Lost if parent isn't ready.

**Why better than alternatives:**
An unbounded queue risks memory exhaustion under load. OpenClaw's pressure-managed queue with caps and expiry is production-ready.

---

### IMP-029: Two-phase commit for external node creation

**Sources:** OC + P (2/3)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
When creating a subgraph execution or spawning an external agent, first create the execution record in state, then initialize the runtime. If runtime initialization fails, roll back the execution record. This prevents orphaned execution records that show "running" but have no live executor.

**Why important overall:**
Creating the record after runtime initialization means a failed init leaves no trace. Creating it before means a successful init can be tracked from the start. The two-phase approach gets both benefits.

**Why important for maistro:**
Our graph executor creates subgraph executions eagerly. If the subgraph fails to initialize (e.g., model not found), the record stays in "running" forever. Two-phase commit cleans this up.

**Why better than current:**
Single-phase creation. Failed initializations leave orphaned "running" records.

**Why better than alternatives:**
Creating the record only on success (lazy creation) means you can't track in-flight creation attempts. Two-phase commit provides observability of the creation process.

---

### IMP-030: Inner/outer loop with follow-up queues

**Sources:** P (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Implement the graph executor as an outer loop that checks for follow-up messages (queued from steering or scheduled triggers) and an inner loop that processes node executions. The outer loop only checks for follow-ups when the inner loop would otherwise stop. This enables "queue next task while current task finishes" patterns.

**Why important overall:**
Without this, follow-up messages are only processed after the entire DAG completes. The inner/outer pattern allows chaining DAGs without waiting for full completion.

**Why important for maistro:**
Our evolution cycle currently runs one genome at a time. With follow-up queues, we can queue the next genome evaluation while the current one is finishing, reducing idle time between evaluations.

**Why better than current:**
Sequential execution only. No follow-up queuing between runs.

**Why better than alternatives:**
A background task queue (Celery, etc.) adds infrastructure. Pi's inner/outer loop is in-process and zero-infrastructure.

---

### IMP-031: Inherited permission restrictions for subgraphs

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
When a subgraph node spawns, carry `allowed_tools` and `denied_tools` lists from the parent. The subgraph's tool registry intersects with these lists. If a parent restricts a tool, the subgraph cannot re-enable it. This creates a security boundary where parent graphs restrict child capabilities.

**Why important overall:**
Without inherited restrictions, a subgraph can access any tool the system offers, even if the parent was restricted. This is a privilege escalation vector.

**Why important for maistro:**
Our graph executor doesn't restrict tool access per-node at all. Any node can use any tool. In a multi-tenant deployment, this means a guest's DAG could access admin tools via subgraphs.

**Why better than current:**
No tool restrictions per-node or per-subgraph. All tools available to all nodes.

**Why better than alternatives:**
Restricting tools at the DAG level (config) is static — it can't adapt based on which node is executing. Per-subgraph inheritance (OpenClaw) is dynamic and composable.

---

### IMP-032: Faux provider for deterministic execution testing

**Sources:** P (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Create `maistro/testing/faux_provider.py` implementing a fully controllable fake LLM that returns pre-seeded responses. Support response sequencing (multiple responses in order), streaming simulation with configurable token sizes, and tool call injection. Register as `faux://test-model` in the model registry.

**Why important overall:**
Testing agent behavior requires deterministic LLM responses. Mocking at the HTTP level is brittle. A faux provider at the model abstraction level is stable and expressive.

**Why important for maistro:**
Our graph executor tests currently either skip LLM-dependent paths or use real API calls (flaky, expensive). A faux provider enables deterministic testing of the entire execution pipeline from DAG input to output without network access.

**Why better than current:**
No test provider. Tests either skip LLM paths or use real API calls.

**Why better than alternatives:**
Mocking `httpx.post` is implementation-specific and breaks when we change the HTTP client. Pi's faux provider mocks at the model abstraction, which is stable across implementation changes.

---

## Category 4: Testing Infrastructure

### IMP-033: Test harness with full wiring factory

**Sources:** P (novel)
**Impact:** P0 Critical
**Difficulty:** add-only

**Plan:**
Create `maistro/testing/harness.py` with a factory function that returns a fully wired `TestEnvironment`: real `Container` with in-memory stores, `ClassifierEngine`, `RouterEngine`, `GraphExecutor`, and `FauxProvider`. Captures all events in an array for assertions. Provides `send_prompt()`, `get_events()`, `get_last_response()` helpers.

**Purpose:**
Enable writing integration tests that exercise the entire pipeline (classify → route → agent → tool → response) without mocks, databases, or network access.

**Why important overall:**
Pi's test harness is the foundation of their 95%+ test coverage. Without it, every test has to manually wire dependencies, leading to inconsistent test setups and missing coverage.

**Why important for maistro:**
Our tests are scattered across packages with inconsistent setup. Some use real SQLite, some mock everything, some use real API calls. A unified harness ensures every test exercises the real pipeline.

**Why better than current:**
Ad-hoc test setup per file. Inconsistent mocking. Some paths untested because setup is too complex.

**Why better than alternatives:**
Pytest fixtures per-module work but don't compose well across test files. A factory function (Pi's approach) is composable, reusable, and provides a consistent API.

---

### IMP-034: Guardrail tests for architectural invariants

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Create `tests/guardrails/` directory with dedicated test files that verify architectural invariants: "subgraph nodes cannot reference non-subgraph executions", "DAG cycles are rejected at validation", "fitness hard gates always apply before Elo bonus", "champion genome is always from the current population". These are separate from functional tests.

**Why important overall:**
Functional tests verify behavior. Guardrail tests verify constraints. Both are needed, but guardrails catch architectural drift that functional tests miss.

**Why important for maistro:**
Our evolution engine has hard gates and invariant properties (e.g., "fitness scores are always non-negative", "population size never drops below minimum"). Guardrail tests lock these in and prevent regressions during refactoring.

**Why better than current:**
No invariant tests. Properties like "hard gates always apply" are assumed but not verified. Refactoring can silently break them.

**Why better than alternatives:**
Property-based testing (Hypothesis) is useful but requires more setup and is non-deterministic. OpenClaw's guardrail tests are deterministic, explicit, and document the invariants for new contributors.

---

### IMP-035: State health probe diagnostic system

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Create `maistro/diagnostics/state_probe.py` with a multi-step diagnostic: create state dir, load SQLite, open database, verify schema version, write-read-delete a test entry, checkpoint WAL. Each step records success/failure with error codes. Expose via `/health/state` endpoint and `maestro doctor state` CLI command.

**Why important overall:**
When state storage breaks (permissions, corruption, schema mismatch), the failure mode is often silent or confusing. A health probe pinpoints exactly which step failed.

**Why important for maistro:**
Our State singleton uses SQLite WAL mode. If WAL gets corrupted or permissions change, the error manifests as "agent not found" or "session not found" — unhelpful. The probe tells us exactly what's broken.

**Why better than current:**
No state health check. Failures are diagnosed by reading error logs and guessing.

**Why better than alternatives:**
A simple "can I connect?" check misses schema version mismatches and WAL corruption. The multi-step probe (OpenClaw) tests every layer of the storage stack.

---

### IMP-036: Seed-and-verify pattern for state tests

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Create test helpers `seed_state(entries)` and `clear_state()` that bulk-insert test data within a write transaction and wipe between tests. Use `INSERT OR REPLACE` to handle idempotent seeding. Ensure WAL is checkpointed after seeding so reads see the data.

**Why important overall:**
SQLite WAL mode means reads from a different connection may not see uncommitted writes from the test setup. Explicit checkpointing after seeding prevents flaky tests.

**Why important for maistro:**
Our SQLite tests occasionally fail with "agent not found" after seeding. This is because the test seeds data in one connection and reads from another without checkpointing WAL. The seed-and-verify pattern fixes this.

**Why better than current:**
Manual SQL inserts in test setup. No checkpointing. Intermittent test failures on WAL reads.

**Why better than alternatives:**
Using `PRAGMA journal_mode=DELETE` in tests avoids WAL issues but doesn't test production configuration. Testing with WAL (and checkpointing correctly) catches WAL-specific bugs.

---

### IMP-037: Regression naming convention with issue tracking

**Sources:** P (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Adopt convention: regression tests go in `tests/regressions/<issue-number>-<short-slug>.test.py`. Add to AGENTS.md or CLAUDE.md. Example: `tests/regressions/042-context-overflow-retry.test.py`. Existing tests stay where they are; only new regressions follow this convention.

**Why important overall:**
When a bug is fixed, the regression test should be findable by issue number. Without a convention, regression tests are scattered and duplicate effort.

**Why important for maistro:**
Our 83 evolution tests are in `packages/maistro-evolve/tests/` but don't reference issue numbers. When a bug reappears, we can't find the original regression test.

**Why better than current:**
No naming convention. Tests named by module (`test_fitness.py`) not by issue.

**Why better than alternatives:**
Adding issue numbers to test docstrings is less discoverable than file-level naming. Pi's directory-based convention makes `git log` and `grep` effective.

---

### IMP-038: Live model switch tests

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Create tests that verify the graph executor correctly transitions between providers mid-DAG without losing context. Gate behind `MAISTRO_LIVE_TEST=1` environment variable. These tests use real API calls and verify that model switching preserves execution state.

**Why important overall:**
Model switching during execution is a critical feature that's hard to test with mocks (the mock doesn't change behavior between providers). Live tests catch real integration issues.

**Why important for maistro:**
Our fallback chains (IMP-013) switch providers mid-execution. Without live tests, we can't verify that the switch actually works end-to-end.

**Why better than current:**
No live integration tests. Provider switching tested only with mocks.

**Why better than alternatives:**
Running live tests on every commit is expensive. Gating behind an env var (OpenClaw) lets CI run fast tests and developers run live tests when needed.

---

### IMP-039: Test helper factories exposed from production modules

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Export a `testing` object from production modules that exposes controlled test-only methods: `testing.sweep_once()`, `testing.set_deps()`, `testing.reset_state()`. These are only used by tests and are clearly separated from the production API. This avoids `patch()` on private methods.

**Why important overall:**
Testing via `patch()` on private methods is brittle — it breaks when internals change. Exposing controlled test helpers is stable because the test author controls the API.

**Why important for maistro:**
Our tests currently `patch("maistro.graph.executor.httpx.AsyncClient")` which breaks if we change HTTP clients. Test helpers would provide a stable interface for dependency injection.

**Why better than current:**
Tests patch private methods. Brittle to internal refactoring.

**Why better than alternatives:**
Dependency injection via constructor parameters works but requires changing every instantiation site. The `testing` export (OpenClaw) is additive — it doesn't change the production API.

## Category 5: State & Session Management

### IMP-040: Tree-structured session history

**Sources:** P + H (2/3)
**Impact:** P1 High
**Difficulty:** refactor

**Plan:**
Change session/execution history from linear lists to tree structures. Each entry has `id`, `parentId`, `timestamp`. A `leaf` pointer tracks the active branch. Support `navigate(targetId)` to move the leaf to any prior entry, creating a branch point. Store as JSONL for append-only writes.

**Purpose:**
Enable branching, forking, and non-linear exploration. A user can try two approaches from the same starting point, keeping both histories.

**Why important overall:**
Both Pi (tree-structured JSONL) and Hermes (session branching) converged on non-linear history. Linear history loses context when users backtrack and try different approaches.

**Why important for maistro:**
Our DAG execution history is linear — each run overwrites the previous context. When the evolution engine explores different configurations, it loses the history of what was tried before. Tree-structured history preserves all exploration paths.

**Why better than current:**
Linear history. Previous runs overwritten. No branching.

**Why better than alternatives:**
Full git-like content-addressed storage (like Jupyter's checkpoint system) is overkill. Pi's parentId-based tree with a leaf pointer is simple and sufficient.

---

### IMP-041: UUIDv7 time-ordered IDs

**Sources:** P (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Replace UUID4 in execution IDs with UUIDv7. UUIDv7 is time-ordered (first 48 bits are millisecond timestamp), which provides natural chronological sorting while remaining globally unique. Truncate to 8 characters for display with collision retry.

**Why important overall:**
UUID4 IDs are random and unsortable. When debugging, you can't tell which execution happened first without joining on timestamps. UUIDv7 gives sortability for free.

**Why important for maistro:**
Our evolution engine generates thousands of genome IDs. Debugging lineage requires chronological ordering. Currently we use UUID4 + separate timestamp field, which requires joins.

**Why better than current:**
UUID4 (random) for IDs. Chronological queries require join on timestamp column.

**Why better than alternatives:**
Auto-increment integers aren't globally unique (problematic across distributed instances). ULIDs are an alternative to UUIDv7 but require an additional dependency. UUIDv7 is standard (RFC 9562) and available in Python's `uuid` module.

---

### IMP-042: Session branching with LLM summarization

**Sources:** P (novel)
**Impact:** P2 Medium
**Difficulty:** add-only (depends on IMP-040)

**Plan:**
When navigating away from a branch (moving the leaf to a different point), optionally summarize the abandoned branch entries using the LLM. Store the summary as a special entry at the branch point. This preserves context about what was explored without keeping full history.

**Why important overall:**
Without summarization, abandoned branches consume storage and context window. Summarization preserves the key learnings while discarding the detail.

**Why important for maistro:**
During tournament battles, losing genomes are discarded. Summarizing their evaluations (what worked, what failed) and attaching to the lineage tree provides valuable context for future evolution cycles.

**Why better than current:**
No branching. No summarization of discarded paths.

**Why better than alternatives:**
Keeping full history of all branches consumes unbounded storage. Pi's summarize-on-abandon pattern is adaptive — it preserves knowledge while managing storage.

---

### IMP-043: Pending writes with batched flush

**Sources:** P (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Buffer state writes (execution updates, fitness scores, population changes) during a DAG run. Flush at defined boundaries: node completion, DAG completion, evolution cycle completion. If the process crashes mid-run, the buffer is lost but the last-flushed state is consistent.

**Why important overall:**
Writing to SQLite on every state change creates WAL contention and slows execution. Buffering writes and flushing at boundaries reduces I/O by 10-100x.

**Why important for maistro:**
Our evolution cycle writes fitness scores to SQLite after every single evaluation. With 50 genomes × 8 benchmarks = 400 writes per cycle, this creates noticeable I/O overhead. Batching into a single write at cycle completion would be faster and more consistent.

**Why better than current:**
Write-through on every state change. High I/O overhead. WAL contention under concurrent writes.

**Why better than alternatives:**
Write-ahead logging (WAL mode) helps but doesn't eliminate the overhead of many small transactions. Pi's pending-write buffer is an application-level optimization that reduces transactions, not just WAL overhead.

---

### IMP-044: Iterative context compaction with structured prompts

**Sources:** H + P (2/3)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
When DAG execution context exceeds a threshold, compress old messages using LLM summarization. Store `_previous_summary` and generate iterative updates ("PRESERVE existing info, ADD new completed actions") instead of re-summarizing from scratch. Use a structured prompt template: Goal, Constraints, Progress, Key Decisions, Next Steps, Critical Context.

**Why important overall:**
Both Hermes and Pi independently built iterative compaction. Non-iterative summarization loses information with each pass. Iterative updates preserve fidelity across multiple compactions.

**Why important for maistro:**
Long-running DAGs accumulate large blackboards. Our graph executor has no compaction mechanism — the blackboard grows until it exceeds the model's context window, then the execution fails. Iterative compaction keeps long-running DAGs alive.

**Why better than current:**
No compaction. Blackboard grows until context overflow, then execution fails.

**Why better than alternatives:**
Simple truncation (drop oldest messages) loses important context. Full re-summarization from scratch is expensive and loses fidelity. Iterative updates (Hermes) are the sweet spot — cheap and faithful.

---

### IMP-045: File operation tracking across compaction

**Sources:** P (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Track which files were read and modified across all messages being compacted. Accumulate the file list and append it to the compaction summary. This ensures the model knows which files were touched even after compaction discards the detailed history.

**Why important overall:**
After compaction, the model has no memory of which files it read or modified. This causes it to re-read files it already processed, wasting tokens.

**Why important for maistro:**
Our graph executor's SCOUT node reads files to prepare context. After compaction, SCOUT might re-read the same files, wasting evaluation time. Tracking prevents this.

**Why better than current:**
No tracking. Compaction loses file access history.

**Why better than alternatives:**
Keeping full history defeats the purpose of compaction. Pi's file-list-append approach preserves the essential info (which files were touched) without the overhead of full history.

---

### IMP-046: Filesystem checkpoint manager with limits

**Sources:** H (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Create `maistro/state/checkpoint.py` implementing transparent filesystem checkpoints with configurable limits: `max_snapshots` (default 10), `max_total_size_mb` (default 100), `max_file_size_mb` (default 10). Checkpoints taken before mutations. Oldest checkpoints pruned when limits exceeded. Rollback restores from checkpoint.

**Why important overall:**
Without checkpoints, a failed mutation leaves the system in an inconsistent state. Checkpoints enable rollback to a known-good state.

**Why important for maistro:**
Our evolution engine's self-improvement loop rewrites prompts. A bad rewrite can degrade fitness. Checkpoints before rewrite enable rollback to the previous prompt if fitness drops.

**Why better than current:**
No checkpoints. Failed mutations leave inconsistent state. Manual rollback required.

**Why better than alternatives:**
Git-based checkpoints add dependency on git being installed. Hermes's filesystem-based approach uses plain file copies and is dependency-free.

---

### IMP-047: Subgraph registry with crash recovery

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Create `SubgraphRegistry` that maintains an in-memory `Map<run_id, SubgraphRecord>` persisted to SQLite. Records track lifecycle phases (created, started, yielded, ended, cleanup) with timestamps. On startup, `restoreOnce()` loads persisted state and reconciles orphaned runs.

**Why important overall:**
Subgraph state is ephemeral in our current system. A crash loses all tracking. The registry provides durability and crash recovery.

**Why important for maistro:**
Our graph executor's subgraph tracking is in-memory only. If the process crashes, all subgraph state is lost. The registry would persist this to SQLite and recover on restart.

**Why better than current:**
In-memory subgraph tracking. Lost on crash. No reconciliation.

**Why better than alternatives:**
Using the main State singleton for subgraph tracking mixes concerns. A dedicated registry (OpenClaw) provides a clean API and isolated storage.

---

### IMP-048: Trajectory recording with bounded size

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Create a JSONL trajectory recorder that captures every DAG node execution, tool call, and model response. Each trajectory file has a configurable byte limit. Events exceeding the per-event limit are truncated with metadata preserving the original byte count. Reserve sentinel bytes for the final truncation event.

**Why important overall:**
Full execution recordings are invaluable for debugging evolution cycles and tournament battles. But they can grow unbounded. Bounded recording provides the debugging value without the disk cost.

**Why important for maistro:**
When the evolution engine produces unexpected results (e.g., fitness plateau), we need to inspect the actual LLM calls to understand why. Trajectory recordings provide this without re-running the evaluation.

**Why better than current:**
No execution recording. Debugging requires re-running evaluations with added logging.

**Why better than alternatives:**
Unbounded recording fills disk. OpenClaw's bounded approach with per-event truncation preserves the structure of the recording while limiting total size.

---

### IMP-049: Hydration from execution history

**Sources:** H + P (2/3)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
When creating a fresh executor instance (e.g., after restart or context switch), reconstruct operational state from execution history rather than starting fresh. Specifically: reconstruct iteration counters from prior turns, reconstruct todo/task lists from most recent tool responses, reconstruct nudge/intervals from conversation patterns.

**Why important overall:**
Both Hermes (gateway session hydration) and Pi (todo store hydration) independently solved the problem of state loss across fresh instances. Without hydration, fresh instances lose all operational context.

**Why important for maistro:**
Our graph executor creates fresh instances for each DAG run. Operational state (retry counters, node completion status, blackboard state) is lost between runs. Hydrating from the execution log preserves continuity.

**Why better than current:**
Fresh instances start with no state. Operational context lost between runs.

**Why better than alternatives:**
Keeping instances alive between runs creates memory leaks. Hermes's approach of hydrating from persistent history on each new instance is more robust.

---

## Category 6: Security

### IMP-050: Comprehensive secret redaction

**Sources:** H + OC (2/3)
**Impact:** P0 Critical
**Difficulty:** add-only

**Plan:**
Create `maistro/security/redact.py` with 30+ regex patterns matching: API key prefixes (sk-, ghp_, AIza, xoxb-, pplx-), ENV assignments, JSON field values, Authorization headers, Telegram bot tokens, private key blocks, database connection strings, JWTs (eyJ...), URL userinfo, URL query parameters. Apply to all log output, error messages, and trajectory recordings. Snapshot `_REDACT_ENABLED` at import time to prevent runtime bypass.

**Why important overall:**
Secrets leak through logs, error messages, and debug output. This is the #1 security risk in agent systems. Both Hermes and OpenClaw independently built comprehensive redaction.

**Why important for maistro:**
Our conductor-router logs full request/response bodies including API keys. Our benchmark runners log LLM responses that may contain leaked credentials from training data. Redaction prevents this.

**Why better than current:**
No secret redaction. API keys, tokens, and credentials appear in logs and error messages.

**Why better than alternatives:**
Simple string replacement of known keys only catches keys you know about. Pattern-based redaction (Hermes) catches keys you haven't seen yet, including keys from providers you don't currently use.

---

### IMP-051: Shell/tool execution consent with drift detection

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Require first-use consent for every (event, command) pair in tool execution. Store approvals in `~/.maistro/tool-consent.json` with `script_mtime_at_approval` for drift detection. If the script is modified after approval, require re-consent. Non-interactive callers must pass `--accept-tools` flag.

**Why important overall:**
Tool execution is the highest-risk agent capability. Without consent, a malicious prompt can execute arbitrary commands. Consent + drift detection ensures the user explicitly approved each tool and is re-notified if the tool changes.

**Why important for maistro:**
Our graph executor's tool nodes execute shell commands and HTTP requests. There is no consent flow. A crafted DAG could execute any command on the host.

**Why better than current:**
No tool consent. All tools available without restriction or approval.

**Why better than alternatives:**
A global "allow all tools" flag is all-or-nothing. Hermes's per-(event,command) approval with drift detection provides granular control while remaining usable.

---

### IMP-052: File safety guards for sensitive paths

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Create `maistro/security/file_guard.py` that prevents writes to sensitive paths: `.ssh/`, `.gnupg/`, `.aws/`, `.env`, credential files. Detect path traversal (`../`) attacks. Return descriptive errors identifying the blocked path and reason.

**Why important overall:**
An agent with file-write capability can steal credentials by writing to `.ssh/authorized_keys` or modify `.env` to inject malicious API endpoints. Path guards prevent this.

**Why important for maistro:**
Our DAG nodes can write files. Without guards, a maliciously-crafted genome from the evolution engine could write to sensitive paths.

**Why better than current:**
No path restrictions. Any node can write to any path the process has access to.

**Why better than alternatives:**
Container-level read-only mounts prevent writes but also prevent legitimate file operations. Hermes's application-level guards are more flexible — they block specific sensitive paths while allowing writes elsewhere.

---

### IMP-053: Message sanitization pipeline

**Sources:** H + P (2/3)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Before every LLM API call, run messages through a sanitization pipeline: (1) surrogate character removal (from clipboard paste of rich text), (2) non-ASCII stripping for ASCII-only providers, (3) orphaned tool result cleanup (results without matching calls), (4) tool-call argument corruption repair (truncated JSON), (5) role-alternation violation repair (consecutive same-role messages).

**Why important overall:**
LLM APIs reject malformed messages with cryptic errors. The sanitization pipeline prevents common malformations that cause silent failures or crashes.

**Why important for maistro:**
Our benchmark runners send prompts with special characters (code snippets, test data). These sometimes contain surrogate characters or truncated JSON that causes the API call to fail with an unhelpful error.

**Why better than current:**
No sanitization. Malformed messages are sent as-is, causing API errors that are attributed to provider failures.

**Why better than alternatives:**
Validating message format at construction time (Pydantic) catches structural errors but not content-level issues like surrogate characters. A pipeline at the call boundary (Hermes) catches everything.

---

### IMP-054: Sandbox runtime status resolution

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Implement `resolve_sandbox_status(session_key, config)` that determines whether a session is sandboxed. Sandboxed sessions cannot: spawn external agents, write to host filesystem, access network resources beyond the configured endpoints. The system provides clear error messages directing users to use `runtime="subgraph"` from sandboxed sessions.

**Why important overall:**
Multi-tenant deployments must isolate user sessions. Without sandbox status, a user's DAG can access another user's data or the host's credentials.

**Why important for maistro:**
Our hive-conductor is a multi-user system (family members + potentially external users). Without sandboxing, any user's DAG can access any other user's data.

**Why better than current:**
No sandboxing. All users share the same execution environment.

**Why better than alternatives:**
Container-per-user isolation is expensive and operationally complex. OpenClaw's logical sandboxing (restricted capabilities per session) is lighter and sufficient for our use case.

---

### IMP-055: DM pairing policy with allowlist

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Default to `auth_policy="pairing"` — unknown senders receive a pairing code instead of agent responses. Explicit `auth_policy="open"` with wildcard allowlist is required for public-facing bots. The `maestro doctor` command surfaces risky auth configurations.

**Why important overall:**
Default-open auth means anyone who discovers the endpoint can use the agent (and incur API costs). Default-paired is secure by default.

**Why important for maistro:**
Our hive-conductor currently has cookie-based auth but no pairing flow. A leaked cookie grants full access. Pairing adds a second factor.

**Why better than current:**
Cookie-based auth only. No pairing flow. No rate limiting per user.

**Why better than alternatives:**
OAuth2 (our current plan for Keycloak migration) handles auth but not authorization. Pairing (OpenClaw) adds device-level authorization that survives cookie rotation.

---

### IMP-056: Non-root container with capability dropping

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Run hive-conductor Docker container as non-root user (`node` uid 1000). Add `cap_drop: [NET_RAW, NET_ADMIN]` and `security_opt: [no-new-privileges:true]` to docker-compose.yml. Pre-create state directory with correct ownership via `RUN install -d -m 0700 -o node -g node /home/node/.maistro`.

**Why important overall:**
Running containers as root is the #1 Docker security anti-pattern. Capability dropping limits the blast radius of container escapes.

**Why important for maistro:**
Our hive-conductor currently runs as root inside the container. A vulnerability in any dependency could grant root-level access to the host.

**Why better than current:**
Container runs as root. No capability restrictions.

**Why better than alternatives:**
Rootless Docker (user namespaces) is more secure but requires host configuration changes. Non-root + capability drop (OpenClaw) works with standard Docker and provides strong protection.

## Category 7: Configuration & Prompting

### IMP-057: Environment variable substitution in config

**Sources:** OC (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Support `${VAR_NAME}` and `${VAR_NAME:-default}` syntax in config YAML values. A resolver scans config after loading, replaces patterns with env var values (or defaults). This allows config files to reference secrets without embedding them and adapt to different environments without modification.

**Why important overall:**
Config files should be committable to version control without containing secrets. Env var substitution is the standard solution (used by Docker Compose, Kubernetes, etc.).

**Why important for maistro:**
Our `system_config.yaml` and `config.yaml` files currently contain hardcoded API keys and connection strings. These can't be committed to git. Env var substitution lets us commit the config structure while keeping secrets in the environment.

**Why better than current:**
Hardcoded values in config files. Secrets committed to git (or excluded from version control entirely).

**Why better than alternatives:**
A separate secrets management tool (Vault, SOPS) adds operational complexity. Env var substitution is zero-dependency and follows the 12-factor app methodology.

---

### IMP-058: Per-provider/per-model timeout resolution chain

**Sources:** H + OC (2/3)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Implement a priority chain for timeout resolution: `providers.<id>.models.<model>.timeout_seconds` > `providers.<id>.timeout_seconds` > `MAISTRO_TIMEOUT` env var > 180s default. Auto-disable stale timeout for local endpoints (localhost/127.0.0.1). Apply to all httpx client construction.

**Why important overall:**
One timeout doesn't fit all. A local Ollama model can respond in seconds. A cloud provider under load can take minutes. Per-model timeouts optimize for both cases.

**Why important for maistro:**
Our benchmark harness uses a single 120s timeout for all providers. Fast models (Cerebras) finish in 2s but wait 118s on timeout. Slow models (GPT-4 on complex prompts) hit the timeout and fail.

**Why better than current:**
Single hardcoded timeout for all providers and models.

**Why better than alternatives:**
Setting timeout per-call (passing it as a parameter) is verbose and error-prone. The resolution chain (Hermes) provides defaults at every level with overrides where needed.

---

### IMP-059: XML-bound prompt sections for clear delimiting

**Sources:** P (novel)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Replace markdown headers (`## Section`) in system prompts with XML tags (`<section_name>content</section_name>`). Apply to benchmark evaluation prompts, DAG node system prompts, and evolution engine self-improvement prompts. XML tags provide unambiguous boundaries that LLMs parse more reliably.

**Why important overall:**
Pi switched from `##` to XML boundaries because agents were ingesting prompt delimiters as content. XML tags have clear open/close semantics that LLMs handle better, especially for nested or multi-line content.

**Why important for maistro:**
Our benchmark prompts use markdown headers. The LLM sometimes includes `##` in its response, confusing the scoring parser. XML boundaries are cleaner for automated parsing.

**Why better than current:**
Markdown headers as prompt delimiters. Ambiguous boundaries. LLM sometimes echoes delimiters.

**Why better than alternatives:**
JSON-wrapped prompts are valid but add escaping overhead. XML tags (Pi) are human-readable, LLM-friendly, and don't require escaping for most content.

---

### IMP-060: Dynamic system prompt generation via callback

**Sources:** P + H (2/3)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Change system prompts from static strings to callbacks `(context) -> str` that receive the execution environment, active tools, model info, and session state. The prompt adapts per-turn (e.g., including only active tools, appending project context, varying guidelines by tool set). Cache the result per-turn for KV cache reuse.

**Why important overall:**
Static prompts waste tokens on irrelevant sections (tools not available, guidelines not applicable). Dynamic prompts include only what's needed, reducing token cost and improving model focus.

**Why important for maistro:**
Our DAG node system prompts are static. A node that only needs the `read_file` tool still gets the prompt for all 15 tools. Dynamic generation reduces prompt size and token cost.

**Why better than current:**
Static system prompts. All content included regardless of relevance.

**Why better than alternatives:**
Pre-building prompts per-config and storing them is static. Per-turn generation (Pi) adapts to runtime state. Hermes's caching ensures KV cache reuse despite dynamic content.

---

### IMP-061: Shell-style argument substitution in templates

**Sources:** P + H (2/3)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Support `$1`, `$@`, `$ARGUMENTS`, `${@:N:L}` positional placeholders in prompt template files (`.md`). A `substitute_args(template, args)` function replaces these with parsed command-line arguments. This enables reusable prompt recipes like `/evaluate $@` or `/benchmark $1 --samples $2`.

**Why important overall:**
Prompt templates should be reusable with different arguments. Without substitution, every variation requires a separate template file.

**Why important for maistro:**
Our benchmark evaluation prompts have per-benchmark variations (different test data, different scoring criteria). Currently each is a separate function. Template substitution would let us use one template per benchmark with argument-driven variation.

**Why better than current:**
Hardcoded prompt strings per benchmark. No template reuse.

**Why better than alternatives:**
Python f-strings work but require the template to be valid Python. Shell-style substitution (Pi) is language-agnostic and works in `.md` files that can be edited by non-programmers.

---

### IMP-062: Config clobber snapshot with bounded rotation

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
When config is overwritten (externally or by the system), save a forensic copy with timestamp suffix (`config.yaml.clobbered.2026-05-19T14-30-00`). Directory-based lock prevents concurrent snapshot corruption. Cap at 32 snapshots; oldest deleted when cap reached. Best-effort — snapshot failure doesn't block the config write.

**Why important overall:**
Config is critical state. If something overwrites it (user mistake, automated tool, bug), you need to know what changed and be able to recover. Snapshots provide forensic history.

**Why important for maistro:**
Our evolution engine's self-improvement loop rewrites prompt configs. If a rewrite produces garbage, we need the previous version to rollback. Clobber snapshots provide this automatically.

**Why better than current:**
No config versioning. Overwrites are destructive. No rollback possible.

**Why better than alternatives:**
Git-tracking config files works but requires committing after every change. OpenClaw's automatic clobber snapshots are zero-friction — they happen transparently.

---

### IMP-063: Profile-based configuration isolation

**Sources:** H (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Support multiple config profiles via `MAISTRO_HOME` environment variable. Each profile has its own `.env`, state database, credential pool, and execution history. Profile switching is a single env var change. Default profile uses `~/.maistro/`.

**Why important overall:**
A single global config means dev, staging, and production share the same credentials and state. Profiles isolate these environments without requiring separate installations.

**Why important for maistro:**
We develop and test on the same machine that runs production. Without profiles, test runs pollute production state and use production credentials.

**Why better than current:**
Single global config. No environment isolation.

**Why better than alternatives:**
Docker containers per environment are heavyweight. Hermes's profile-based isolation via env var is lightweight and works with existing tooling.

---

### IMP-064: Language-aware output adaptation

**Sources:** H (novel)
**Impact:** P3 Low
**Difficulty:** minor-change

**Plan:**
Detect the language of user input and produce responses (summaries, error messages, compaction summaries) in the same language. Apply to the graph executor's compaction prompt and the evolution engine's self-improvement feedback.

**Why important overall:**
Multilingual users get confused when summaries switch to English mid-conversation. Language-aware output preserves conversation coherence.

**Why important for maistro:**
Low priority but relevant if we internationalize. Not needed for current English-only usage.

**Why better than current:**
All output in English regardless of input language.

**Why better than alternatives:**
Explicit language selection per-session adds UI friction. Hermes's auto-detection from conversation history is seamless.

---

### IMP-065: Prompt cache TTL configuration

**Sources:** H (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Support configurable cache TTL: `none` (no caching), `short` (5min, default), `long` (1h, 2x cost on write but amortizes across long sessions). Map to provider-specific implementations: Anthropic `cache_control.ttl`, OpenAI `prompt_cache_retention`. Configure per-node in DAG config.

**Why important overall:**
Prompt caching saves 90% on input tokens for repeated prompts. But the TTL matters — short TTL is cheaper per write, long TTL amortizes better for long-running sessions.

**Why important for maistro:**
Our evolution engine evaluates the same benchmark prompt structure thousands of times with slight variations. Prompt caching could reduce costs significantly. Configurable TTL lets us use `short` for quick evaluations and `long` for tournament battles.

**Why better than current:**
No prompt caching configuration. Provider defaults apply (usually no caching or short TTL).

**Why better than alternatives:**
Always using `long` TTL wastes money on one-shot evaluations. Configurable per-node TTL (Hermes) optimizes cost per use case.

---

### IMP-066: Resource loader for multi-source config

**Sources:** P + OC (2/3)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Create `ResourceLoader` that abstracts loading configs, prompts, and templates from multiple sources: user config directory (`~/.maistro/`), project directory (`.maistro/`), and built-in defaults. Deduplicates and merges resources by name, with later sources overriding earlier ones. Produces a unified resource set for the session.

**Why important overall:**
Configs come from multiple places (user preferences, project requirements, system defaults). A unified loader handles precedence and merging.

**Why important for maistro:**
Our benchmark configs, DAG templates, and prompt templates are scattered across packages. Some in YAML, some in Python, some hardcoded. A unified resource loader provides a single discovery mechanism.

**Why better than current:**
Ad-hoc loading per module. No precedence rules. No deduplication.

**Why better than alternatives:**
A plugin-based config system (like Hydra) adds a heavy dependency. Pi's ResourceLoader is a simple abstraction that handles the common case.

---

## Category 8: Observability & Diagnostics

### IMP-067: Session-scoped log tagging

**Sources:** H + OC (2/3)
**Impact:** P1 High
**Difficulty:** minor-change

**Plan:**
Implement `set_log_context(run_id, node_id)` that tags all log records on the current thread with the DAG run ID and current node ID. Use Python's `logging.LoggerAdapter` or `contextvars`. Enable `maestro logs --run <id>` to filter a single DAG run from the centralized logs. Clear context on run completion.

**Why important overall:**
When multiple DAG runs execute concurrently, logs from different runs are interleaved. Without tagging, debugging a specific run requires manual filtering by timestamp and pattern matching.

**Why important for maistro:**
Our evolution cycle runs multiple evaluations concurrently. Log output from different genomes is interleaved, making it impossible to trace a single genome's evaluation. Run-scoped tagging solves this.

**Why better than current:**
No log context. All logs interleaved. Manual filtering required.

**Why better than alternatives:**
Separate log files per run creates file management overhead. Context-based tagging (Hermes) uses a single log stream with structured filtering.

---

### IMP-068: Rate limit telemetry with utilization display

**Sources:** H (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Parse `x-ratelimit-*` HTTP response headers into `RateLimitState` with four buckets (requests/min, requests/hr, tokens/min, tokens/hr). Display as ASCII progress bars in CLI output and as numeric gauges in the evolution dashboard. Warn at 80%+ utilization. Expose via `/health/rate-limits` endpoint.

**Why important overall:**
Rate limits are the primary throughput bottleneck for API-heavy systems. Without visibility, users can't tell if they're hitting limits or have headroom.

**Why important for maistro:**
Our evolution cycle can hit provider rate limits during aggressive evaluation. Without telemetry, we can't tell if a slow cycle is due to rate limits or model latency. The dashboard should show rate limit utilization in real-time.

**Why better than current:**
No rate limit tracking. No visibility into provider utilization.

**Why better than alternatives:**
Simple "remaining requests" counter misses the multi-bucket nature of rate limits (requests/min vs requests/hr vs tokens/min). Hermes's four-bucket system is more accurate.

---

### IMP-069: Stream diagnostic header capture

**Sources:** H (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
During streaming LLM calls, capture HTTP response headers, exception chains, and retry metadata into a `StreamDiagnostics` object. Attach to the execution log entry. Enable post-mortem diagnosis of streaming failures (partial responses, dropped connections, provider-specific errors).

**Why important overall:**
Streaming failures are hard to debug because the error occurs mid-stream and the response headers are lost. Capturing them enables post-mortem analysis.

**Why important for maistro:**
Our benchmark runners use streaming for large evaluations. When a stream fails partway through, we currently have no diagnostic data — just "stream interrupted". Header capture tells us whether it was a provider timeout, rate limit, or content filter.

**Why better than current:**
No stream diagnostics. Failed streams produce "stream error" with no details.

**Why better than alternatives:**
Enabling debug logging on httpx captures headers but also produces overwhelming output for successful streams. Hermes's targeted capture (only on failure) is more efficient.

---

### IMP-070: Doctor/health diagnostic command

**Sources:** H + OC (2/3)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Create `maestro doctor` CLI command that checks: Python version, model connectivity, tool availability, credential validity, state database health, disk space, and config validity. Each check produces pass/fail/warn with actionable fix suggestions. Expose as `/health/diagnostic` API endpoint.

**Why important overall:**
Both Hermes and OpenClaw have doctor commands. When something breaks, users need a single command that tells them what's wrong and how to fix it.

**Why important for maistro:**
Our system has many moving parts (LiteLLM, SQLite, graph executor, evolution engine). When something fails, diagnosis currently requires reading logs, checking config, and testing connectivity manually. A doctor command automates this.

**Why better than current:**
No diagnostic command. Manual troubleshooting required.

**Why better than alternatives:**
A health endpoint (we have `/health`) only checks if the server is running. A doctor command (Hermes) checks whether it's working correctly — model connectivity, credential validity, state health.

---

### IMP-071: Activity tracking for timeout diagnostics

**Sources:** H (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Track `_last_activity_ts`, `_last_activity_desc`, and `_current_node` on the graph executor. Update on each API call, node execution, and stream chunk. When a timeout fires, include the last activity in the error message: "DAG timed out after 300s. Last activity: node 'scout' calling gpt-4 at T+287s."

**Why important overall:**
Timeout errors without context are useless. "DAG timed out" doesn't tell you which node was slow or what it was doing. Activity tracking provides the context.

**Why important for maistro:**
DAG timeouts are common during benchmark evaluation. Without knowing which node was running when the timeout fired, we can't optimize. Activity tracking identifies the bottleneck.

**Why better than current:**
Timeout errors with no context. No indication of which node was running.

**Why better than alternatives:**
Logging every activity at INFO level creates noise. Hermes's approach of tracking activity metadata and surfacing it only on timeout is zero-cost on the happy path.

---

### IMP-072: Trajectory deep sanitization for safe logging

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Apply to trajectory recordings before writing: (1) recursive depth limiting (max 6 levels), (2) array truncation (max 64 items), (3) string truncation (max 32K chars), (4) secret redaction via IMP-050. Detect circular references via `WeakSet`. This ensures trajectory logs never contain secrets or blow up disk.

**Why important overall:**
Trajectory recordings capture full LLM inputs/outputs. These can contain secrets (API keys in prompts), huge responses (base64 images), or circular references (tool call chains). Sanitization makes logs safe to share.

**Why important for maistro:**
Our benchmark evaluation recordings contain model prompts that include test data and scoring criteria. Some test data includes credential-like strings. Sanitization ensures we can share recordings for debugging without leaking secrets.

**Why better than current:**
No sanitization. Recordings may contain secrets. Cannot be safely shared.

**Why better than alternatives:**
Simply not recording sensitive data limits debugging capability. OpenClaw's sanitize-then-record approach preserves debugging value while ensuring safety.

---

### IMP-073: Per-subsystem scoped loggers

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Create `create_subsystem_logger(name)` factory that returns a logger with a subsystem prefix. Example: `create_subsystem_logger("graph/executor")` produces logs like `[graph/executor] Node 'scout' completed in 2.3s`. Enable per-subsystem log level configuration: `MAISTRO_LOG_LEVEL_GRAPH=DEBUG`.

**Why important overall:**
A single flat logger makes it impossible to filter logs by subsystem. Scoped loggers enable `maestro logs --subsystem evolution` to see only evolution-related output.

**Why important for maistro:**
Our logs currently use `logging.getLogger(__name__)` which produces Python module paths (`maistro.graph.executor`). Subsystem names (`graph/executor`, `evolution/cycle`, `benchmark/ragas`) are more meaningful for operators.

**Why better than current:**
Module-path-based logger names. No subsystem grouping.

**Why better than alternatives:**
Structured logging (JSON) is useful for machine consumption but harder to read in terminals. OpenClaw's scoped loggers with prefix formatting are human-friendly.

## Category 9: Infrastructure & Deployment

### IMP-074: Lazy dependency loading

**Sources:** H + P + OC (3/3)
**Impact:** P1 High
**Difficulty:** refactor

**Plan:**
Defer heavy imports (Playwright, browser automation, TTS engines, PDF libraries, optional providers) until the module that needs them is actually called. Create `maistro/lazy.py` with `lazy_import(module_name, attr_name)` that returns a proxy object importing on first attribute access. Keep startup time under 500ms for common use cases.

**Why important overall:**
All three frameworks independently built lazy loading. It's table-stakes for agent systems with many optional dependencies. Startup time directly impacts developer experience and server cold-start latency.

**Why important for maistro:**
Our benchmark runners import all 8 benchmark modules at startup, even if only running one. Each imports its own dependencies (some heavy). Lazy loading would let us import only the needed benchmark.

**Why better than current:**
All imports at module level. Startup time includes all dependencies regardless of usage.

**Why better than alternatives:**
Dynamic `importlib.import_module()` calls scattered in code are error-prone. A centralized lazy import helper (Hermes's `_OpenAIProxy` pattern) is reusable and testable.

---

### IMP-075: Multi-stage Docker with pinned SHA256 digests

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** refactor

**Plan:**
Refactor Dockerfile into four stages: (1) workspace-deps (extract package.json/pyproject.toml), (2) build (install + compile), (3) runtime-assets (prune dev deps, strip .pyc/.pyo), (4) runtime (slim base). Pin base images to SHA256 digests for reproducible builds. Dependabot refreshes digests.

**Why important overall:**
Docker layer caching and reproducible builds are standard best practices. Unpinned base images can change between builds, introducing unexpected behavior.

**Why important for maistro:**
Our hive-conductor Docker image uses a single-stage build with unpinned base images. Builds are slow (no layer caching) and non-reproducible.

**Why better than current:**
Single-stage build. Unpinned base images. No layer caching optimization.

**Why better than alternatives:**
BuildKit cache mounts help with layer caching but don't solve reproducibility. SHA256 pinning (OpenClaw) solves both.

---

### IMP-076: Pre-created state directory with correct ownership

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Add `RUN install -d -m 0700 -o app -g app /home/app/.maistro` to Dockerfile. This ensures Docker named volumes inherit `app` ownership instead of `root` (the default when Docker creates the volume directory). Verify with `stat` after creation.

**Why important overall:**
When Docker creates a named volume mount point, it uses root ownership. The application process (running as non-root) then can't write to it. Pre-creating with correct ownership prevents this.

**Why important for maistro:**
Our hive-conductor container writes to `/vmpool/docker/` which is root-owned. The app process runs as root to work around this. With pre-created directories, we could run as non-root (IMP-056).

**Why better than current:**
App runs as root to work around volume ownership issues.

**Why better than alternatives:**
`chown` in entrypoint scripts adds startup latency and race conditions. Pre-creation in Dockerfile (OpenClaw) is deterministic.

---

### IMP-077: Optional extension packages via build args

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Add `MAISTRO_EXTENSIONS` Docker build arg accepting comma-separated extension names (e.g., `browser,voice,canvas`). The build stage selectively copies only the needed package files. A post-build prune removes unused extension dist directories. This reduces image size by excluding unused extensions.

**Why important overall:**
Full-featured agent images can be 2-5GB. Most deployments use a subset of features. Optional extensions let users build lean images.

**Why important for maistro:**
Our hive-conductor image includes all packages (maistro-core, maistro-canvas, maistro-evolve). Users who only need the API don't need canvas or evolution. Optional build args let them exclude these.

**Why better than current:**
All packages included in every build. Full image regardless of usage.

**Why better than alternatives:**
Separate Dockerfiles per variant is maintenance-heavy. OpenClaw's build-arg approach uses one Dockerfile with conditional stages.

---

### IMP-078: Docker GPG key fingerprint verification

**Sources:** OC (novel)
**Impact:** P3 Low
**Difficulty:** minor-change

**Plan:**
When installing packages from third-party apt repositories in Dockerfile, verify the GPG key fingerprint matches the expected value. Validate the key contains exactly one public key to prevent multi-key trust escalation.

**Why important overall:**
Supply chain attacks via compromised apt repositories are a real threat. Fingerprint verification prevents accepting malicious keys.

**Why important for maistro:**
Low priority — our Docker image doesn't install from third-party apt repos. Relevant only if we add external repos in the future.

**Why better than current:**
No GPG verification. Implicit trust of all repository keys.

**Why better than alternatives:**
Not installing from third-party repos at all avoids the issue. If needed, fingerprint verification (OpenClaw) is the correct mitigation.

---

### IMP-079: Container path isolation from host environment

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change

**Plan:**
Pin container-side paths in docker-compose.yml (`MAISTRO_STATE_DIR=/home/app/.maistro`) to prevent host environment variables (like macOS paths from `.env` files) from leaking into the Linux container. Explicitly set all path env vars in the container definition.

**Why important overall:**
When docker-compose reads `.env` from the host, path variables like `STATE_DIR=/Users/dev/.maistro` leak into the container where `/Users/dev` doesn't exist. This causes cryptic `mkdir` errors.

**Why important for maistro:**
Our docker-compose.yml reads `.env` from `/root/docker/hive-conductor/`. Host-side paths would break inside the container. Explicit path pinning prevents this.

**Why better than current:**
Environment variables from host `.env` leak into container. Path-related failures on different host OS.

**Why better than alternatives:**
Using only docker-compose `environment:` section (no `.env` file) prevents leaks but makes local development harder. Pinning container paths (OpenClaw) lets both work correctly.

---

### IMP-080: Lockstep monorepo versioning

**Sources:** P (novel)
**Impact:** P3 Low
**Difficulty:** minor-change

**Plan:**
All packages in the monorepo share the same version number. The release script bumps all packages together, finalizes changelogs, commits, tags, and publishes. This eliminates version compatibility confusion — any combination with the same version works.

**Why important overall:**
Independent versioning in a monorepo creates dependency hell. "Does maistro-core 0.5.2 work with maistro-evolve 0.3.1?" Lockstep versioning eliminates this question.

**Why important for maistro:**
Our four packages (maistro-core, maistro-canvas, maistro-server, maistro-turing) have independent versions. Compatibility is implicit and untested. Lockstep versioning makes it explicit.

**Why better than current:**
Independent versioning per package. Compatibility not guaranteed.

**Why better than alternatives:**
A compatibility matrix documentation is a maintenance burden. Lockstep versioning (Pi) is zero-maintenance — same version = compatible.

---

### IMP-081: Supply-chain advisory checking

**Sources:** H (novel)
**Impact:** P3 Low
**Difficulty:** add-only

**Plan:**
Add `pip-audit` or `safety` to CI pipeline. Scan dependencies for known vulnerabilities on every push. Block merge if critical vulnerabilities found. Run weekly scheduled scan for new advisories in existing dependencies.

**Why important overall:**
Dependencies can introduce vulnerabilities. Automated scanning catches known CVEs before they reach production.

**Why important for maistro:**
Low priority — our dependencies are primarily well-maintained libraries (pydantic, httpx, fastapi). But as we add more providers and tools, the attack surface grows.

**Why better than current:**
No dependency vulnerability scanning.

**Why better than alternatives:**
Dependabot (GitHub-native) covers GitHub Actions but not Python dependencies. `pip-audit` covers PyPI dependencies specifically.

---

## Category 10: Tool System & Extensibility

### IMP-082: Before/after execution hooks with block/override semantics

**Sources:** H + P + OC (3/3)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Define `before_node(node_config, context) -> HookResult` and `after_node(node_config, context, result) -> HookResult` on the graph executor. `before_node` can return `{block: True, reason: "..."}` to prevent execution. `after_node` can override content, error status, or set `terminate` flag. Hooks are registered globally and per-node-type.

**Why important overall:**
All three frameworks independently built before/after hook systems. Hooks enable: approval flows (block on sensitive operations), output sanitization (redact secrets from results), early termination (stop on critical failure), and metrics collection (timing, cost tracking). Without hooks, every cross-cutting concern must be woven into the execution loop.

**Why important for maistro:**
Our graph executor has no hook system. Adding metrics, logging, or approval flows requires modifying the executor itself. Hooks let us add these concerns externally.

**Why better than current:**
No hooks. All cross-cutting concerns hardcoded in executor.

**Why better than alternatives:**
Decorator-based hooks (Python) work for functions but not for async graph execution. The protocol-based hook approach (Pi) is explicit, typed, and composable.

---

### IMP-083: Schema sanitizer for local inference compatibility

**Sources:** H + OC (2/3)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Create `maistro/tools/schema_sanitizer.py` that strips `pattern` and `format` JSON Schema keywords from tool schemas before sending to local inference servers (llama.cpp, vLLM, Ollama). These keywords break llama.cpp's json-schema-to-grammar converter. Apply automatically when the provider is detected as local (localhost/127.0.0.1).

**Why important overall:**
Tool schemas designed for cloud providers (with regex patterns and format constraints) break local inference servers. The sanitizer makes the same schemas work everywhere.

**Why important for maistro:**
Our evolution engine should be able to evaluate genomes against local models (cheaper, faster, private). But our tool schemas use `pattern` and `format` keywords that crash llama.cpp. The sanitizer bridges this gap.

**Why better than current:**
Tool schemas work only on cloud providers. Local inference fails with schema errors.

**Why better than alternatives:**
Maintaining separate schemas for local and cloud is duplication. Hermes's automatic sanitization based on provider detection is zero-maintenance.

---

### IMP-084: Tool guardrail with hash-based loop detection

**Sources:** H (novel)
**Impact:** P1 High
**Difficulty:** add-only

**Plan:**
Create `ToolGuardrail` that tracks tool call signatures (tool name + SHA-256 of canonical args). Detect three patterns: (1) exact repeated failure (same call, same args, same error), (2) same-tool failures (any args, same tool, any error), (3) idempotent no-progress (same read-only call returning same result hash). Configurable `warn_after` and `block_after` thresholds per pattern.

**Why important overall:**
Agents can get stuck in tool loops — calling the same failing operation repeatedly. The guardrail detects these loops and either warns the model or hard-stops the execution.

**Why important for maistro:**
Our graph executor's nodes can loop on failed LLM calls (retry the same prompt). The guardrail would detect this and force a different approach instead of wasting API credits.

**Why better than current:**
No loop detection. Nodes retry until max-retry is exhausted, wasting tokens on each identical attempt.

**Why better than alternatives:**
Simple retry counting (our current approach) counts attempts but doesn't detect that they're identical. Hash-based dedup (Hermes) detects when the agent is truly stuck vs. when it's making progress with different approaches.

---

### IMP-085: Plugin state with SQLite schema versioning

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Extend our State singleton with plugin-scoped state storage using `PRAGMA user_version` for schema versioning. Plugin state table with composite primary key `(plugin_id, namespace, entry_key)`. WAL mode with automatic checkpointing. Lazy-opened per-plugin database file in the state directory.

**Why important overall:**
Plugins need persistent state but shouldn't access the core state directly. Schema versioning prevents corruption when plugin versions change.

**Why important for maistro:**
Our evolution engine needs to persist population state, tournament rankings, and lineage history. Currently these are in-memory. Plugin-state storage provides a clean API for this without modifying the core State singleton.

**Why better than current:**
In-memory population state. Lost on restart. No plugin state isolation.

**Why better than alternatives:**
Using the main State singleton for everything creates a single point of failure and schema coupling. OpenClaw's per-plugin state isolation is cleaner.

---

### IMP-086: Keyed state stores with per-namespace limits and TTL

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** add-only (depends on IMP-085)

**Plan:**
On top of plugin state (IMP-085), add per-namespace `maxEntries` with FIFO eviction and `defaultTtlMs` for auto-expiry. When a new entry exceeds the limit, the oldest is deleted. Options validated for consistency across reopens — reopening with different limits throws an error.

**Why important overall:**
State stores without limits grow unbounded. Namespace limits + TTL provide automatic storage management without manual cleanup.

**Why important for maistro:**
Our tournament leaderboard grows with every battle. Without limits, it eventually consumes all available storage. Namespace limits + TTL would keep the leaderboard trimmed to recent results.

**Why better than current:**
No storage limits. No TTL. State grows until disk is full.

**Why better than alternatives:**
Manual cleanup scripts are forgettable. OpenClaw's automatic FIFO eviction + TTL is set-and-forget.

---

### IMP-087: Atomic registerIfAbsent for idempotent writes

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change (depends on IMP-085)

**Plan:**
Implement `register_if_absent(key, value) -> bool` using `INSERT OR IGNORE` within a write transaction. Returns `True` only if the insert succeeded (key didn't exist). This provides atomic idempotent writes without read-then-write races. Combined with TTL, enables one-shot state entries.

**Why important overall:**
The read-then-write pattern (check if exists, then insert) has a race condition where two concurrent processes both read "not exists" and both insert. Atomic `INSERT OR IGNORE` prevents this.

**Why important for maistro:**
Our evolution cycle marks genomes as "evaluated" to avoid duplicate evaluations. The current read-then-write pattern allows two concurrent cycles to evaluate the same genome. Atomic register-if-absent prevents this.

**Why better than current:**
Non-atomic read-then-write for idempotency checks. Race conditions possible.

**Why better than alternatives:**
Application-level locking (threading.Lock) doesn't work across processes. SQLite `INSERT OR IGNORE` (OpenClaw) is process-safe and zero-overhead.

---

### IMP-088: Consume operation for one-shot read-and-delete

**Sources:** OC (novel)
**Impact:** P2 Medium
**Difficulty:** minor-change (depends on IMP-085)

**Plan:**
Implement `consume(key) -> Optional[value]` that atomically reads a value and deletes it within a single write transaction. Only one consumer can read a given entry. This is the "claim a work item" pattern for distributed task queues or approval flows.

**Why important overall:**
When multiple consumers process a queue, the read-then-delete pattern has a race where two consumers read the same item. Atomic consume prevents double-processing.

**Why important for maistro:**
Our evolution engine's breeding queue should be consumed atomically — each parent pair should be bred by exactly one cycle instance. Currently, concurrent cycles can breed the same pair twice.

**Why better than current:**
Non-atomic read-then-delete. Double-processing possible under concurrency.

**Why better than alternatives:**
A dedicated task queue (Celery, RQ) is overkill for our use case. SQLite atomic consume (OpenClaw) is lightweight and sufficient.

---

### IMP-089: Extension system with typed lifecycle events

**Sources:** P + H (2/3)
**Impact:** P2 Medium
**Difficulty:** add-only

**Plan:**
Define an extension protocol with `setup(context)` function receiving typed context with hooks for: session events (`on_run_start`, `on_run_end`), tool registration, command registration, and custom stream functions. Extensions can register custom providers, add tools, inject system prompt sections, and provide UI components. An `ExtensionRunner` manages lifecycle, error isolation, and cleanup.

**Why important overall:**
Both Pi (extension system) and Hermes (plugin system) built typed extension protocols. Extensions enable community contributions without modifying core code. Error isolation ensures one bad extension doesn't crash the system.

**Why important for maistro:**
Our benchmark runners should be extensions — each benchmark registers its tools, prompt templates, and scoring functions. Currently they're hardcoded into the harness. Extension-izing them enables adding new benchmarks without modifying the evolution engine.

**Why better than current:**
Benchmarks hardcoded in harness. Adding a new benchmark requires modifying core files.

**Why better than alternatives:**
A simple plugin discovery (import all files in `plugins/` directory) provides extensibility but no lifecycle management or error isolation. Pi's typed extension protocol is more robust.

---

## Prioritized Implementation Roadmap

Items are grouped by tier and ordered by dependency. Items in the same group can be implemented in parallel.

### Tier P0 — Critical (blocks production use)

These items form the reliability foundation. Without them, the system is fragile under real-world conditions.

**Wave 1: Error & Credential Foundation (no dependencies)**

| ID | Item | Difficulty | Est. LOC |
|----|------|-----------|----------|
| IMP-001 | Error classification pipeline | add-only | ~300 |
| IMP-003 | Jittered exponential backoff | add-only | ~80 |
| IMP-010 | Guaranteed completion events | refactor | ~150 |
| IMP-011 | Multi-credential pool | add-only | ~250 |
| IMP-050 | Secret redaction | add-only | ~200 |

**Wave 2: Depends on Wave 1**

| ID | Item | Difficulty | Est. LOC |
|----|------|-----------|----------|
| IMP-002 | Transient vs permanent disambiguation | minor-change | ~120 |
| IMP-012 | API key rotation with cycling | add-only | ~150 |
| IMP-021 | IterationBudget shared across subgraphs | add-only | ~100 |
| IMP-022 | Phase machine for lifecycle | refactor | ~200 |
| IMP-033 | Test harness factory | add-only | ~300 |

### Tier P1 — High (next sprint)

These items provide major quality and reliability improvements.

**Wave 3: Graph Execution Hardening**

| ID | Item | Difficulty | Est. LOC |
|----|------|-----------|----------|
| IMP-004 | Context-overflow inference | minor-change | ~60 |
| IMP-005 | Anti-thrashing guard | minor-change | ~50 |
| IMP-006 | Grace window for deferred cleanup | minor-change | ~80 |
| IMP-007 | Dead connection cleanup | minor-change | ~40 |
| IMP-008 | Cross-process rate limit coordination | minor-change | ~100 |
| IMP-009 | Stage-aware retry policies | add-only | ~80 |
| IMP-013 | Fallback chain with primary restore | add-only | ~150 |
| IMP-023 | Hierarchical depth/role system | add-only | ~80 |
| IMP-024 | Event sink pattern | refactor | ~200 |

**Wave 4: Testing & State Infrastructure**

| ID | Item | Difficulty | Est. LOC |
|----|------|-----------|----------|
| IMP-016 | Context length probing | add-only | ~100 |
| IMP-018 | Auth profile cooldown tracking | add-only | ~120 |
| IMP-020 | OAuth proactive refresh | minor-change | ~60 |
| IMP-026 | Orphaned execution detection | add-only | ~150 |
| IMP-027 | Stale run detection with sweeper | minor-change | ~100 |
| IMP-029 | Two-phase commit for node creation | minor-change | ~80 |
| IMP-031 | Inherited permission restrictions | minor-change | ~60 |
| IMP-032 | Faux provider for testing | add-only | ~200 |
| IMP-034 | Guardrail tests for invariants | add-only | ~200 |
| IMP-035 | State health probe | add-only | ~100 |
| IMP-036 | Seed-and-verify for state tests | minor-change | ~80 |
| IMP-039 | Test helper factories | minor-change | ~100 |

**Wave 5: Core Architecture**

| ID | Item | Difficulty | Est. LOC |
|----|------|-----------|----------|
| IMP-014 | Cross-process OAuth sync | minor-change | ~80 |
| IMP-025 | Steering / mid-run guidance | add-only | ~120 |
| IMP-040 | Tree-structured session history | refactor | ~200 |
| IMP-043 | Pending writes with batched flush | minor-change | ~80 |
| IMP-044 | Iterative context compaction | add-only | ~200 |
| IMP-047 | Subgraph registry with recovery | add-only | ~150 |
| IMP-049 | Hydration from execution history | minor-change | ~100 |
| IMP-051 | Tool execution consent | add-only | ~150 |
| IMP-052 | File safety guards | add-only | ~80 |
| IMP-053 | Message sanitization pipeline | add-only | ~150 |
| IMP-054 | Sandbox runtime status | add-only | ~100 |
| IMP-057 | Env var substitution in config | add-only | ~80 |
| IMP-058 | Per-provider timeout chain | add-only | ~60 |
| IMP-059 | XML-bound prompt sections | minor-change | ~40 |
| IMP-067 | Session-scoped log tagging | minor-change | ~60 |
| IMP-070 | Doctor diagnostic command | add-only | ~200 |
| IMP-074 | Lazy dependency loading | refactor | ~100 |
| IMP-082 | Before/after execution hooks | add-only | ~150 |
| IMP-083 | Schema sanitizer for local inference | add-only | ~80 |
| IMP-084 | Tool guardrail with loop detection | add-only | ~120 |

### Tier P2 — Medium (near-term)

**Wave 6: Polish & Configuration**

| ID | Item | Difficulty | Est. LOC |
|----|------|-----------|----------|
| IMP-015 | Automatic API mode detection | minor-change | ~60 |
| IMP-017 | Provider-specific headers | add-only | ~60 |
| IMP-019 | External CLI auth discovery | add-only | ~100 |
| IMP-028 | Suspended delivery queue | add-only | ~120 |
| IMP-030 | Inner/outer loop with follow-ups | add-only | ~100 |
| IMP-037 | Regression naming convention | minor-change | ~0 |
| IMP-038 | Live model switch tests | add-only | ~100 |
| IMP-041 | UUIDv7 time-ordered IDs | minor-change | ~40 |
| IMP-042 | Session branching with summarization | add-only | ~120 |
| IMP-045 | File operation tracking | minor-change | ~60 |
| IMP-046 | Checkpoint manager with limits | add-only | ~150 |
| IMP-048 | Trajectory recording | add-only | ~150 |
| IMP-055 | DM pairing policy | add-only | ~80 |
| IMP-056 | Non-root container | minor-change | ~30 |
| IMP-060 | Dynamic system prompt | minor-change | ~80 |
| IMP-061 | Argument substitution in templates | add-only | ~60 |
| IMP-062 | Config clobber snapshots | add-only | ~80 |
| IMP-063 | Profile-based config isolation | add-only | ~100 |
| IMP-065 | Prompt cache TTL config | minor-change | ~40 |
| IMP-066 | Resource loader for multi-source | add-only | ~100 |
| IMP-068 | Rate limit telemetry | add-only | ~100 |
| IMP-069 | Stream diagnostic capture | add-only | ~80 |
| IMP-071 | Activity tracking for timeouts | minor-change | ~40 |
| IMP-072 | Trajectory sanitization | add-only | ~80 |
| IMP-073 | Per-subsystem scoped loggers | minor-change | ~40 |
| IMP-075 | Multi-stage Docker | refactor | ~80 |
| IMP-076 | Pre-created state directory | minor-change | ~10 |
| IMP-077 | Optional extension build args | minor-change | ~40 |
| IMP-079 | Container path isolation | minor-change | ~20 |
| IMP-085 | Plugin state with schema versioning | add-only | ~150 |
| IMP-086 | Keyed state stores with limits | add-only | ~80 |
| IMP-087 | Atomic registerIfAbsent | minor-change | ~40 |
| IMP-088 | Consume operation | minor-change | ~40 |
| IMP-089 | Extension system with lifecycle | add-only | ~200 |

### Tier P3 — Low (when convenient)

| ID | Item | Difficulty | Est. LOC |
|----|------|-----------|----------|
| IMP-064 | Language-aware output | minor-change | ~40 |
| IMP-078 | Docker GPG fingerprint check | minor-change | ~20 |
| IMP-080 | Lockstep monorepo versioning | minor-change | ~60 |
| IMP-081 | Supply-chain advisory checking | add-only | ~30 |

---

## Summary Statistics

| Category | P0 | P1 | P2 | P3 | Total |
|----------|----|----|----|----|-------|
| 1. Error Handling & Resilience | 3 | 6 | 0 | 0 | 9 |
| 2. Model Management & Credentials | 2 | 5 | 2 | 0 | 9 |
| 3. Graph Execution Architecture | 2 | 8 | 2 | 0 | 12 |
| 4. Testing Infrastructure | 1 | 5 | 2 | 0 | 8 |
| 5. State & Session Management | 0 | 6 | 4 | 0 | 10 |
| 6. Security | 1 | 5 | 2 | 0 | 8 |
| 7. Configuration & Prompting | 0 | 3 | 6 | 1 | 10 |
| 8. Observability & Diagnostics | 0 | 3 | 4 | 0 | 7 |
| 9. Infrastructure & Deployment | 0 | 1 | 5 | 2 | 8 |
| 10. Tool System & Extensibility | 0 | 3 | 5 | 0 | 8 |
| **Total** | **9** | **45** | **32** | **3** | **89** |

**Estimated total LOC: ~8,500** (excluding tests)
**Estimated implementation time: 6-8 weeks for P0+P1, 4-6 weeks for P2**
