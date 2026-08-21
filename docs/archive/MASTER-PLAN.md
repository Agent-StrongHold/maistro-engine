# Hive Conductor — Master Cutover Plan

> **⚠️ HISTORICAL (archived 2026-06-20).** Most of this plan shipped (Docker Compose
> structure, config schema, base porting). The genuinely still-open items — hosted curl
> installer, GHCR image publishing, full frontend page coverage, MCP server
> implementations, remaining Project mAIstro feature ports — are tracked as
> `[engine-100]`–`[engine-104]` in `BACKLOG.md`. See also the companion
> `docs/archive/PRODUCT-SPEC.md`. Kept for historical design-rationale reference.

**Product**: Hive Conductor — Multi-agent AI platform
**Codebase**: maistro-engine monorepo (`maistro-core`, `maistro-server`, `maistro-turing`, `maistro-canvas`)
**Date**: 2026-05-12
**Status**: Active build plan

---

## Product Architecture

### Install Experience

Users never clone the repo. They run:

```bash
curl -fsSL https://get.hiveconductor.com | bash
```

Or visit `https://install.hiveconductor.com` for a web wizard that generates the curl command with their choices baked in.

The installer:
1. Detects OS (Linux, macOS, WSL2)
2. Installs Docker + Docker Compose if missing
3. Creates `~/hive-conductor/` with docker-compose.yml, .env, config.yaml
4. Pulls pre-built images from GHCR
5. Starts the stack
6. Opens `http://localhost:8101`

### Services

| Service | Image | Port | Purpose |
|---|---|---|---|
| hive-conductor | `ghcr.io/blakematthews-dev/hive-conductor` | 8101 | FastAPI app + React SPA |
| postgres | `postgres:16` | 5432 | Persistence |
| redis | `redis:7-alpine` | 6379 | Sessions + caching + task queue |
| litellm | `ghcr.io/berriai/litellm` | 4000 | Model gateway (or bring your own) |
| langfuse | `langfuse/langfuse` | 3100 | Observability (optional) |
| mcp-sandbox | `ghcr.io/blakematthews-dev/mcp-sandbox` | — | Code execution |
| mcp-git | `ghcr.io/blakematthews-dev/mcp-git` | — | Git/GitHub |
| mcp-browser | `ghcr.io/blakematthews-dev/mcp-browser` | — | Browser automation |
| mcp-ha | `ghcr.io/blakematthews-dev/mcp-ha` | — | Home Assistant (optional) |

### Dockerfile

Multi-stage production build:
- Stage 1: Python builder — install maistro-core + maistro-server + maistro-turing
- Stage 2: Node builder — build React SPA
- Stage 3: Runtime — copy wheels + static files, minimal image, `CMD uvicorn maistro_server.main:app`

---

## Source Map: Where Every Piece Comes From

### From Stronghold (~70% of backend, newest + most mature)

| Subsystem | Source Location | Lines | Tests | What Gets Ported |
|---|---|---|---|---|
| Persistence | `stronghold/persistence/` + `migrations/` | 1,160 + 631 SQL | 682 | 8 pg_* stores + 13 SQL migrations (strip `org_id`) |
| Agent framework | `stronghold/agents/` | ~2,000 | 240+ | Base class, factory, 16 agents, 6 strategies |
| Builder pipeline | `stronghold/builders/` | ~1,200 | 200+ | Spec → test → code → review pipeline |
| Router | `stronghold/router/` | — | 836 | Tests only (code is same as maistro-core per ADR-019). Add `smart_home`/`video_gen` speed weights from conductor-router |
| Classifier | `stronghold/classifier/` | — | 337 | Tests only. Add domain indicators from conductor-router |
| Memory | `stronghold/memory/` + `sessions/` | ~1,778 | 3,946 | SessionSummarizer (148 lines), stricter scope matching, tests |
| Security | `stronghold/security/` | ~3,935 | 4,038 | CasbinToolPolicy, production middleware, tests |
| Agents (diff) | `stronghold/agents/` | — | 240+ | Update maistro-core where Stronghold moved forward |
| A2A delegation | `stronghold/a2a/` | ~650 | 50+ | Agent-to-agent delegation + lifecycle |
| Events/Reactor | `stronghold/events.py` + `triggers.py` | 721 | existing | 1000Hz event loop + 10 registered triggers |
| Scheduling | `stronghold/scheduling/` + `api/routes/schedules.py` | 375 | existing | Cron CRUD store + 7 REST API endpoints (strip `org_id`) |
| Tools | `stronghold/tools/` | ~4,063 | 5,682 | ShellExecutor, FileOps, WorkspaceManager, GitHubToolExecutor, SSRF/DNS rebinding protection, quality gates |
| API server | `stronghold/api/` | ~5,800 | 100+ | Route patterns, admin surface, middleware stack |

All Stronghold code gets `org_id` columns and WHERE clauses stripped. Hive Conductor is single-user. Stronghold keeps its own multi-tenant copy.

### From Project mAIstro (~20% of backend, all genuinely unique)

| Subsystem | Source Location | Lines | What Gets Ported |
|---|---|---|---|
| Bouncer | `conductor/orchestrator/agents/bouncer.py` | 451 | Phase 0 pre-screener with PASS/REJECT/CLARIFY verdicts. 20+ regex patterns covering token injection, malware, privilege escalation that Warden lacks |
| Agent Factory | `agents/variant_selector.py` + `recipe.py` + `structured_output.py` + `schemas.py` | ~700 | Thompson sampling for prompt variant selection, YAML agent recipes, typed output validation with Pydantic, 11 agent role definitions |
| Agent Spawner | `agents/spawner.py` | 557 | Central spawn entry point with inter-agent output screening (prevents trust propagation between agents) |
| APM | `memory/apm.py` | 282 + 166 template | Agent Personality Matrix: identity, values, communication style, standing orders, guardrails, relationships, self-knowledge. YAML-based, diffable, git-trackable |
| Dream Loop | `agents/experimental/dream_loop.py` | 216 | Idle-time memory consolidation: reinforce strong memories, prune weak, generate counterfactuals from regrets (every 3rd), distill WISDOM (every 10th, lessons reinforced 5+ times) |
| Heartbeat | `orchestrator/heartbeat.py` | 827 | Autonomous initiative engine: 13 subsystems on periodic cycle (APM reload, standing orders, mood, memory review, dream loop, skill forge, red team, stress rehearsal, auto-remediation, morning digest) |
| Mood Ring | `agents/experimental/temporal.py` | ~100 | System health (disk%, GPU temp, quota pressure) → mood (ADVENTUROUS/NORMAL/CAUTIOUS/CONSERVATIVE) → controls exploration rate, dream/stress/red-team enablement |
| Red Team | `agents/experimental/red_team.py` | 369 | Self-hardening security: red agent generates attacks (memory-integrated, avoids repeats), tests against Bouncer, blue agent analyzes bypasses, suggests rules posted to message board for human review (never auto-applied) |
| Skill Forge | `agents/experimental/skill_forge.py` | 291 | Self-authoring skills: LLM drafts SKILL.md → Warden scans own creation → installs at Skull tier → records as affirmation → posts to message board |
| Evolution History | `memory/evolution.py` | 191 | Git-tracked mutation audit trail for all memory/APM changes |
| Message Board | `memory/board.py` | 159 | Proactive agent→human async communication with webhook delivery |
| Context Archaeology | `agents/experimental/phantom.py` | 266 | Forensic analysis of failed tasks: reconstructs decision chain, identifies root cause, generates targeted fix suggestions |
| Tournament Arena | `agents/experimental/tournament.py` | 199 | Private model leaderboard from real task outcomes (not generic benchmarks) |
| Prompt Evolver | `agents/prompt_evolver.py` | 371 | Automated A/B testing of prompts: promotes challengers beating production by >5% over 50+ runs |
| Trace Reviewer | `agents/trace_reviewer.py` | 580 | Periodic analysis of Langfuse traces, training data, and gateway metrics |
| Abra (HA agent) | `agents/abra.py` | 1,065 | Intelligent Home Assistant integration with room context, device inventory, environmental awareness |
| Temporal Patterns | `agents/experimental/temporal.py` | ~140 | Time capsules (scheduled self-reminders) + temporal pattern recognition from episodic memory |
| Stress Rehearsal | `agents/experimental/stress_rehearsal.py` | 372 | Controlled chaos testing: container stop/restart, disk pressure, dependency testing. Protected containers, max 60s disruption, always restores |
| Vault Sync | `interfaces/vault_sync.py` | 340 | Obsidian/CouchDB/Syncthing integration for vault-based task submission |
| Langfuse Tracer | `gateway/langfuse_tracer.py` | 435 | Trace propagation for multi-agent: gateway generations nest under conductor trace tree |
| Layered Prompts | `memory/layer0.py` + `layer1.py` | 202 | L0 = pinned constraints (content-hash cached), L1 = working memory per-task (auto-compress) |
| Ultra Think | `gateway/ultra_think.py` | 334 | Parallel diverse generation: N completions with varied sampling profiles (conservative/standard/exploratory/creative/focused) |
| Slot Manager | `gateway/slot_manager.py` | 261 | KV cache slot lifecycle for local inference (llama-server) with lane-aware scheduling |
| Prefix Cache | `gateway/prefix_cache.py` | 196 | Per-project KV cache persistence with content-hash invalidation |
| Tenant Context | `orchestrator/tenant.py` | 143 | ContextVar-based multi-tenant flow (for Stronghold compatibility) |
| Changelog | `memory/changelog.py` | 80 | Append-only JSONL audit trail |
| Exemplar Library | `training/exemplar_library.py` | 95 | Few-shot example management |
| Training Data | `training/data_collector.py` | 120 | Fine-tuning data collection from task outcomes |

All Project mAIstro features get feature-flagged behind toggles in config.yaml.

### From Turing Research (maistro-turing package, parallel track)

maistro-turing porting runs independently. Does not block Hive Conductor from working.

**Current state**: Phase 1 of 7 complete (types, protocols, tiers, bridge, self-model types, 4 producers, 28 tests).

| Phase | What | Source | Lines | Duration |
|---|---|---|---|---|
| Phase 2 | Persistence (SQLite + PG repos) | `sketches/turing/repo.py` + `postgres_repo.py` | ~963 | 1 day |
| Phase 3 | Retrieval + write paths | `retrieval.py` + `write_paths.py` + `embedding_index.py` | ~548 | 1 day |
| Phase 4 | Cognition modules | `motivation.py` + `dreaming.py` + `daydream.py` + `tuning.py` + `scheduler.py` + `detectors/` + 8 producers | ~3,400 | 1.5 days |
| Phase 5 | Self-model | `self_repo.py` (1,288) + `self_surface.py` + `self_conduit.py` + activation graph + mood + nodes + todos + bootstrap + 20 guardrail modules | ~7,500 | 2 days |
| Phase 6 | Runtime | `runtime/main.py` (2,405) + `chat.py` (1,276) + reactor + journal + tools + providers | ~5,000 | 1.5 days |
| Integration | Turing ↔ Hive Conductor via bridge adapters, feature-flagged | — | — | 1 day |

When `TURING_ENABLED=true` in config, Hive Conductor gains a self. When false, standard multi-agent orchestrator.

### From conductor-router (~5% — homelab glue only)

| Subsystem | Source Location | Lines | What Gets Ported |
|---|---|---|---|
| HA tools | `app/tools.py` (HA sections) | ~175 | `ha_control`, `ha_list_devices`, `ha_notify`, `family_chores` → MCP server |
| Utility tools | `app/tools.py` (utility sections) | ~230 | `web_search`, `system_info`, `weather`, `timezone`, `dns` → MCP server |
| CoinSwarm tools | `app/tools.py` (trading sections) | ~140 | Query/action/market endpoints → MCP server |
| Reminders | `app/tools.py` (reminder sections) | ~70 | Set/list reminders via learnings store → MCP tool |
| Tool loop | `app/main.py` (tool loop section) | ~200 | 3-round classify→tool→learn cycle into Conduit pipeline |
| Config hot-reload | `app/main.py` | ~50 | mtime-check + lock pattern, `POST /admin/reload` endpoint |

All wrapped as MCP servers using `fastmcp`.

### New Build

| Subsystem | Lines (est.) | What |
|---|---|---|
| Frontend (React SPA) | ~18,500 | 10 pages + shared components (see `design/PRODUCT-SPEC.md`) |
| Dockerfile (multi-stage) | ~50 | Python builder → Node builder → minimal runtime |
| config.yaml.example | ~200 | Default model configs + routing params + feature flags + tool definitions |
| install/install.sh | ~300 | Curl-able installer script |
| install/web-wizard/ | ~2,000 | Static site for web install wizard |

---

## Execution: 8 Waves

### Wave 0: Docker Compose Stack (4 hours)

**Goal**: `docker compose up` starts everything. Health checks pass.

| Task | Detail |
|---|---|
| Create Dockerfile | Multi-stage: Python builder → Node builder → runtime. `CMD uvicorn maistro_server.main:app --host 0.0.0.0 --port 8000` |
| Create docker-compose.yml | 8 services: hive-conductor, postgres, redis, litellm, langfuse, mcp-sandbox, mcp-git, mcp-browser |
| Create .env.example | All config vars with sensible defaults |
| Create config.yaml.example | 5 models, 5 task types, routing params, tool definitions, feature flags |
| Create install/install.sh | Curl-able installer: detect OS, install Docker if needed, create dir, pull images, start stack |
| Network layout | Internal network for services, exposed ports: 8101 (API+UI), 4000 (LiteLLM), 3100 (Langfuse) |
| Volumes | postgres-data, redis-data, hive-config (config.yaml persistence) on a persistent Docker volume |
| Verify | `docker compose up` → all containers healthy → `curl :8101/health` returns OK |

### Wave 1: Persistence (1 day)

**Goal**: Postgres with real schema, migrations run on startup.

| Task | Source | Detail |
|---|---|---|
| Port SQL migrations | Stronghold `migrations/` (13 files) | Strip `org_id`, adapt table names. Key tables: agents, prompts, sessions, quota_usage, learnings, audit_log, outcomes, scheduled_tasks, task_executions, skills, mcp_servers |
| Port pg_* stores | Stronghold `persistence/` (8 files) | Strip `org_id` parameters and WHERE clauses |
| Port scheduling store | Stronghold `scheduling/store.py` (215 lines) | Cron CRUD + validation, strip `org_id` |
| Wire container.py | maistro-core | Postgres stores when `DATABASE_URL` set, InMemory fallback when not |
| Port persistence tests | Stronghold (~682 lines) | Adapt for single-tenant |

### Wave 2: Backend Core from Stronghold (2 days)

**Goal**: Full pipeline works: classify → route → agent → response through Postgres-backed stores.

| Task | Source | Detail |
|---|---|---|
| Diff router | Stronghold vs maistro-core | Keep maistro-core code (canonical per ADR-019). Port 836 lines of tests. Add `smart_home`/`video_gen` speed weights from conductor-router |
| Diff classifier | Stronghold vs maistro-core | Keep maistro-core code. Port 337 lines of tests. Add domain indicators (family names, trading, smart_home) from conductor-router |
| Diff memory | Stronghold vs maistro-core | Port SessionSummarizer (148 lines). Port 3,946 lines of tests |
| Diff security | Stronghold vs maistro-core | Port CasbinToolPolicy (optional). Port production middleware (security headers, rate limit, payload size). Port 4,038 lines of tests |
| Diff agents | Stronghold vs maistro-core | Update where Stronghold moved forward. Port 240+ agent tests, 90+ strategy tests, 200+ builder tests |
| Diff A2A | Stronghold vs maistro-core | Verify current. Port 50+ tests |
| Diff conduit/container | Stronghold vs maistro-core | Verify current — this is the backbone |
| Port events/reactor | Stronghold `events.py` + `triggers.py` | 1000Hz event loop + 10 registered triggers |
| Port tools framework | Stronghold `tools/` | ShellExecutor, FileOps, WorkspaceManager, GitHubToolExecutor, SSRF/DNS rebinding protection, quality gates |

### Wave 3: Unique Capabilities from Project mAIstro (2 days, starts after Wave 2)

**Goal**: Autonomous agent features that no other codebase has.

| Task | Source | Detail |
|---|---|---|
| Port Bouncer | `bouncer.py` (451 lines) | Phase 0 pre-screener. Merge 10 regex patterns into Warden. Three verdicts: PASS/REJECT/CLARIFY. Integration point: conduit.py, before Gate scan |
| Port Agent Factory | 4 files (~700 lines) + 11 YAML recipes | Thompson sampling, declarative YAML agent definitions, typed output validation (Pydantic schema → JSON injection → validation → retry) |
| Port Spawner | `spawner.py` (557 lines) | Central spawn entry: fill role defaults, variant selection, schema injection, Langfuse span, prompt assembly, gateway call, structured output parsing, inter-agent output screening |
| Port APM | `apm.py` (282 + 166 lines) | Agent personality matrix. 7-section YAML. Injected into system prompt by Spawner |
| Port Dream Loop | `dream_loop.py` (216 lines) | Idle-time consolidation. Triggered by heartbeat when no tasks pending |
| Port Heartbeat | `heartbeat.py` (827 lines) | Autonomous initiative engine. Background asyncio task in server lifespan. 13 subsystems |
| Port Mood Ring | `temporal.py` (~100 lines) | System health → mood → behavior adjustment |
| Port Red Team | `red_team.py` (369 lines) | Self-hardening security. Weekly trigger from heartbeat |
| Port Skill Forge | `skill_forge.py` (291 lines) | Self-authoring skills. Daily trigger from heartbeat |
| Port Message Board | `board.py` (159 lines) | Proactive agent→human async communication |
| Port Evolution History | `evolution.py` (191 lines) | Git-tracked mutation audit trail |
| Port remaining | ~15 smaller modules (~4,500 lines) | Context archaeology, tournament arena, prompt evolver, trace reviewer, Abra (HA), temporal patterns, stress rehearsal, vault sync, Langfuse tracer, ultra-think, slot manager, prefix cache, layered prompts, changelog, exemplars, training data collector, tenant context |
| Feature-flag all | — | Every subsystem behind a toggle in config.yaml |

### Wave 4: Homelab Tools from conductor-router (1 day, parallel with Wave 3)

**Goal**: HA, search, weather, reminders as MCP tools.

| Task | Source | Detail |
|---|---|---|
| Create MCP HA server | conductor-router `tools.py` + Project mAIstro `abra.py` | `ha_control`, `ha_list_devices`, `ha_notify`, `family_chores`. Use Abra for intelligent HA interaction |
| Create MCP utils server | conductor-router `tools.py` | `web_search`, `weather`, `timezone`, `dns`, `system_info` |
| Create MCP trading server | conductor-router `tools.py` | CoinSwarm query/action/market |
| Create MCP reminders | conductor-router `tools.py` | Set/list reminders backed by Postgres |
| Port tool loop logic | conductor-router `main.py` | 3-round classify→tool→learn into Conduit pipeline |
| Port config hot-reload | conductor-router `main.py` | mtime-check + lock, `POST /admin/reload` |

### Wave 5: Frontend UI (3 days, starts after Wave 2, parallel with Waves 3-4)

**Goal**: Full web portal served from FastAPI as static files.

| Day | Task | Detail |
|---|---|---|
| Day 1 | Scaffold + Chat + Settings | React + Vite + Tailwind + shadcn/ui. Chat page with SSE streaming, tool call panels, clarification UI. Settings page with config, models, auth, features |
| Day 2 | Missions + Schedules + Triggers | Mission submission with clarification loop, progress timeline, update thread. Cron editor, trigger builder (interval/event/state), execution history |
| Day 3 | Skills + Agents + MCP + Memory + CLI + Containers | Marketplace + AI builder + import wizard + security scan for skills/agents/MCP. Memory tier browser. xterm.js terminal. Container builder wizard |

All pages, endpoints, and features are specified in `design/PRODUCT-SPEC.md`.

### Wave 6: Config + End-to-End Wiring (1 day)

**Goal**: Fresh config.yaml, everything wired, smoke tests pass.

| Task | Detail |
|---|---|
| Create config.yaml | 5 models (claude-sonnet, gemini-flash, llama-4-scout, qwen2.5-coder local, gpt-4.1-mini), 5 task types (chat, code, research, creative, tool_dispatch), routing (quality_weight=0.6, cost_weight=0.4), tool definitions, feature flags |
| Wire config loading | Lifespan hook: config.yaml → MaistroYamlConfig → set_yaml_config() → RouterEngine + ClassifierEngine + tool registry |
| Wire LiteLLM client | `LiteLLMClient` wrapper around `litellm.acompletion` → LLMClient protocol → Container |
| Wire tool registry | MCP servers registered in Container, discoverable by agents via ToolRegistry |
| Wire Conduit pipeline | Bouncer → Gate → Classifier → Router → Agent → Tool dispatch → Learning extraction → Response |
| Wire heartbeat | Background asyncio task in lifespan, feature-flagged |
| Smoke test | Chat (streaming), tool dispatch ("turn off living room light" → HA MCP), task submission, scheduling, persistence verification |

### Wave 7: Integration + Cutover (1 day)

**Goal**: Running alongside conductor-router, then replace it.

| Task | Detail |
|---|---|
| OpenWebUI integration | Add Hive Conductor (`:8101`) as model provider in OpenWebUI (`:3200`). Keep conductor-router (`:8100`) as existing provider |
| Parallel run | Route conversations through both. Compare: classification accuracy, model selection quality, response time, tool dispatch correctness |
| Verify persistence | Learnings, sessions, outcomes all persisting to Postgres |
| Verify homelab tools | HA control, family chores, notifications, search, weather all work through new MCP servers |
| Traefik cutover | Change `conductor.example.com` route from `:8100` to `:8101` when stable |
| Conductor-router withers | Keep running but no longer primary |

---

## Timeline

| Wave | Duration | Start | End | Dependencies |
|---|---|---|---|---|
| Wave 0 | 4 hours | Day 1 AM | Day 1 | None |
| Wave 1 | 1 day | Day 1 | Day 1 | Wave 0 |
| Wave 2 | 2 days | Day 1 | Day 3 | Wave 0 |
| Wave 3 | 2 days | Day 3 | Day 5 | Wave 2 |
| Wave 4 | 1 day | Day 3 | Day 4 | Wave 0 (parallel with Wave 3) |
| Wave 5 | 3 days | Day 3 | Day 6 | Wave 2 (parallel with Waves 3-4) |
| Wave 6 | 1 day | Day 5 | Day 6 | Waves 1+2+3+4+5 |
| Wave 7 | 1 day | Day 6 | Day 7 | Wave 6 |
| **Total** | **~7 days** | | | |

**Critical path**: Wave 0 → Wave 1 → Wave 6 → Wave 7. Everything else parallelizes.

---

## Feature Flags (from Day 1)

```yaml
features:
  turing_enabled: false
  heartbeat_enabled: false
  dream_loop_enabled: false
  red_team_enabled: false
  skill_forge_enabled: false
  stress_rehearsal_enabled: false
  ultra_think_enabled: false
  bouncer_enabled: true
  evolution_tracking: true
  message_board_enabled: true
  prompt_evolver_enabled: false
  tournament_enabled: false
  mood_ring_enabled: false
  temporal_patterns_enabled: false
```

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Stronghold code diverged from maistro-core more than expected | Days of rework | Wave 2 diff first, before any porting |
| Turing bridge adapters break when maistro-core APIs change | Turing won't start | Test bridge adapters against real maistro-core |
| Project mAIstro experimental features crash under load | Unreliable autonomous behavior | Feature-flag everything, default off |
| LiteLLM shared instance can't handle two consumers | Rate limiting / quota conflicts | Dedicated LiteLLM for Hive Conductor if needed |
| 13 SQL migrations don't run cleanly against fresh Postgres | Stack won't start | Test migrations in CI |
| conductor-router homelab tools depend on hardcoded IPs/URLs | Won't work with different network | Parameterize via env vars / config.yaml |
| Dockerfile multi-stage build too large | Slow pull times | Minimize runtime stage, use slim base |

---

## Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-12 | Product name: Hive Conductor | All surfaces available (PyPI, GitHub, .com, .ai). "The Conductor" as shorthand. |
| 2026-05-12 | Deployment: docker-compose only | Regular people can't handle k3s. One command install. Stronghold gets k3s/Helm separately. |
| 2026-05-12 | Install: curl script + web wizard | No git clone. Pre-built images from GHCR. Config files are the product surface. |
| 2026-05-12 | Frontend: React + Vite + Tailwind | Web UI is the case where JS/TS is the right tool per user's rule. |
| 2026-05-12 | Stronghold is primary source (~70%) | Newest code, 4,233 tests, wired enforcement, real persistence, protocol-driven DI |
| 2026-05-12 | Project mAIstro is secondary source (~20%) | 18 genuinely unique capabilities (Bouncer, Agent Factory, Dream Loop, Heartbeat, etc.) |
| 2026-05-12 | conductor-router withers | Homelab glue (5%) gets wrapped as MCP tools. Monolithic single-file architecture dies. |
| 2026-05-12 | maistro-turing is parallel track | Does not block Hive Conductor. Feature-flagged. |
| 2026-05-12 | CLI-Anything is external integration | Separate GitHub repo. Provides headless Inkscape/Gimp via terminal UI. Not imported into maistro-core. |
