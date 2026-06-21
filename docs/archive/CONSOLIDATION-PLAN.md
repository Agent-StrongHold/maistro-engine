# Maistro Engine — Consolidation Master Plan

> **⚠️ HISTORICAL (archived 2026-06-20).** The monorepo consolidation described below has
> shipped — see ADR-019 and ADR-030 (both reference this doc) and the `packages/` layout
> in `CLAUDE.md`. The handful of items that were still open when this plan was archived
> (Master Orchestrator security gate + API wiring) are tracked as `[engine-105]` in
> `BACKLOG.md`. Kept for historical trace of the consolidation rationale and subsystem
> provenance mapping.

**Canonical shape (2026-05):** `maistro-engine` is the primary substrate monorepo; wholesale absorption of sibling product trees (older mega-merge drafts) stays **deferred**. Prefer additive `packages/*` and `apps/*`, registry/spec pulls, and Copier rebases over flattening repos.

**Date:** 2026-05-01
**Status:** Active
**Target:** `<workspace-root>/maistro-engine/`
**Sources:** Stronghold (`<workspace-root>/stronghold/`), Project mAIstro (`<workspace-root>/Project_mAIstro/`), conductor-router (`<workspace-root>/conductor-router/`)

---

## Architecture

```
maistro-engine/                          # Monorepo root
├── packages/
│   ├── maistro-core/                    # Shared library — pip install maistro-core
│   │   └── src/maistro/
│   │       ├── agents/                  # Agent framework + roster (renameable)
│   │       ├── a2a/                     # Agent-to-Agent delegation
│   │       ├── builders/                # Builder pipeline (Frank/Mason/Auditor)
│   │       ├── classifier/              # Intent classification (3-phase)
│   │       ├── config/                  # Settings + config loading
│   │       ├── memory/                  # Learnings, episodic, scopes, outcomes
│   │       ├── observability/           # Logging, metrics, tracing
│   │       ├── orchestrator/            # Master Orchestrator + Super Planner
│   │       ├── protocols/               # Abstract interfaces (DI)
│   │       ├── router/                  # Scoring utility + ModelRouter protocol
│   │       ├── scheduler/               # Heartbeat / proactive autonomy
│   │       ├── security/                # Warden, Sentinel, trust boundaries
│   │       ├── skills/                  # Marketplace, Forge, canary, scanning
│   │       ├── tasks/                   # Task queue, runner, models
│   │       ├── tools/                   # Sandbox, git, browser, file ops
│   │       └── types/                   # Shared type definitions
│   │
│   ├── maistro-server/                  # FastAPI app — thin wrapper
│   │   └── src/maistro_server/
│   │       ├── api/                     # HTTP routes (chat, tasks, webhooks, etc.)
│   │       └── main.py                  # FastAPI app factory
│   │
│   └── maistro-turing/                  # Autonoetic self-model extensions
│       └── src/maistro_turing/
│           ├── self_model/              # Identity, mood, prospection
│           ├── dreaming/                # Daydreaming, dreaming, motivation
│           ├── producers/               # Blog, journal, outreach, hobbies
│           └── runtime/                 # Actor, chat, providers, tools
```

---

## Subsystem Inventory — What Ports From Where

### From Stronghold (enterprise-grade, 2785+ tests)

| Subsystem | Stronghold Source | maistro-core Destination | Lines | Tests |
|-----------|------------------|-------------------------|-------|-------|
| **Agent Framework** | `agents/base.py`, `agents/factory.py` | `agents/` | ~1050 | 150+ |
| **Agent Roster** (renameable) | `agents/{artificer,scribe,forge,warden_at_arms,auditor,mason,frank}/` | `agents/{code,write,create,control,review,build,decompose}/` | ~700 | 80+ |
| **Reasoning Strategies** | `agents/strategies/{react,plan_execute,direct,delegate,builders_learning,tool_http}.py` | `agents/strategies/` | ~811 | 90+ |
| **Builder Pipeline** | `builders/{contracts,runtime,orchestrator,verifier,spec_emitter,spec_coverage,spec_templates,property_gen,logger,services}.py` | `builders/` | ~1200 | 200+ |
| **A2A Delegation** | `a2a/{delegate,lifecycle,guest_peers}.py` | `a2a/` | 650 | 50+ |
| **Memory — Learnings** | `memory/learnings/{store,extractor,promoter}.py` | `memory/learnings/` | ~400 | 60+ |
| **Memory — Episodic** | `memory/episodic/{store,tiers,retrieval}.py` | `memory/episodic/` | ~250 | 40+ |
| **Memory — Scopes** | `memory/scopes.py`, `memory/outcomes.py`, `memory/mutations.py` | `memory/` | ~200 | 30+ |
| **Warden** | `security/warden/{patterns,heuristics,sanitizer,detector,flag_response,semantic}.py` | `security/warden/` | ~800 | 100+ |
| **Sentinel** | `security/sentinel/{policy,validator,audit,pii_filter,token_optimizer}.py` | `security/sentinel/` | ~400 | 50+ |
| **Classifier** | `classifier/{engine,keyword,llm_fallback,complexity,multi_intent,logging}.py` | `classifier/` | ~500 | 60+ |
| **Router** | `router/{scorer,selector,filter,scarcity,speed}.py` | `router/` | ~350 | 50+ |
| **Skills — Marketplace** | `skills/{marketplace,forge,parser,registry,catalog,connectors,canary,fixer,loader}.py` | `skills/` | ~2300 | 150+ |
| **Protocols** | `protocols/{agents,llm,memory,classifier,router,quota,tools,skills,embeddings,...}.py` | `protocols/` | ~600 | 40+ |
| **Types** | `types/{agent,memory,intent,model,security,config,skill,spec,feedback,tool,...}.py` | `types/` | ~800 | 30+ |
| **Persistence** | `persistence/{pg_agents,pg_learnings,pg_outcomes,pg_audit,pg_sessions,pg_quota,pg_prompts}.py` | `persistence/` | ~700 | 40+ |

### From Project mAIstro (original conductor)

| Subsystem | mAIstro Source | maistro-core Destination | Notes |
|-----------|---------------|-------------------------|-------|
| **Agent Spec** | `orchestrator/agents/agent_spec.py` | `agents/spec/` | Already in T1 |
| **Spawner** | `orchestrator/agents/spawner.py` | `agents/spawner/` | Already in T1 |
| **Variant Selector** | `orchestrator/agents/variant_selector.py` | `agents/spawner/` | Already in T1 |
| **Recipes** | `orchestrator/agents/recipe.py`, `recipes/` | `agents/recipes/` | Already in T1 |
| **Structured Output** | `orchestrator/agents/structured_output.py` | `agents/spec/` | Already in T1 |
| **Memory Layers** | `orchestrator/memory/{layer0,layer1,layer2,episodic,knowledge_graph}.py` | `memory/` | Superseded by Stronghold version |
| **Prompt Manager** | `orchestrator/prompts/prompt_manager.py` | `config/` | Merge with Stronghold's |
| **Exemplar Library** | `orchestrator/training/exemplar_library.py` | `memory/` | Ultra Think training data |
| **Skill Scanner** | `orchestrator/skills/scanner.py` | `skills/` | Merge with Stronghold's |

### From conductor-router (running homelab instance)

| Subsystem | conductor-router Source | maistro-core Destination | Notes |
|-----------|----------------------|-------------------------|-------|
| **Router** | `app/router.py` | `router/` | Dict-based → port to typed |
| **Classifier** | `app/classifier.py` | `classifier/` | Simpler version, merge |
| **Quota Tracker** | `app/quota.py` | `router/` | SQLite → port to protocol |
| **Sessions** | `app/sessions.py` | `sessions/` | In-memory → port to protocol |
| **Learnings** | `app/learnings.py` | `memory/learnings/` | Simpler version, merge |
| **Forge** | `app/forge.py` | `skills/forge.py` | Skill creation |
| **Tools** | `app/tools.py` | `tools/` | HA control, browser, chores |
| **Security** | `app/security/` | `security/` | Warden subset |

---

## Sibling product specs (`Project_mAIstro/specs/`)

The **canonical product + gateway backlog** lives in the **sibling repo** (same parent directory as `maistro-engine` by default):

| Location | Role |
|----------|------|
| `../Project_mAIstro/specs/` | Numbered `S-NNN-*.md` and area folders (`conductor/`, `security/`, `tools/`, `channels/`, `infra/`, …). **Not copied** into this monorepo. |

**Workflow (must be pulled in, not ignored):**

1. Keep `Project_mAIstro` cloned **beside** `maistro-engine` (or set `MAISTRO_PRODUCT_REPO` to an absolute path).
2. Before engine / Flutter / protocol work that traces to product behavior, run **`./scripts/pull-sibling-product-specs.sh`** (or `git -C "$MAISTRO_PRODUCT_REPO" pull --ff-only`) so your checkout matches what you are implementing.
3. In **maistro-engine PRs**, link the driving spec(s): e.g. `Project_mAIstro/specs/conductor/S-158-*.md` (path + commit SHA or branch). Paste short excerpts only when the link is not enough for reviewers.

**Engine-only specs** remain under `maistro-engine/docs/specs/SPEC-*.md` (substrate, bootstrap, Hive, Flutter node acceptance, etc.).

---

## Agent Roster — Renamable via agent.yaml

Every agent is **data, not code**. The `agent.yaml` defines identity and can be renamed freely.
Strategy code is shared — only the YAML config changes.

| Stronghold Name | Default maistro Name | Role | Strategy |
|----------------|---------------------|------|----------|
| Artificer | Code Agent | Multi-phase engineering (plan → code → test → fix → commit) | plan_execute |
| Scribe | Write Agent | Writing specialist with committee review | plan_execute |
| Forge | Create Agent | Tool/skill creation, starts at skull trust tier | react |
| Warden-at-Arms | Control Agent | Device control, API calls, runbook execution | react |
| Auditor | Review Agent | PR review, security checks, mock detection, spec coverage | direct |
| Frank | Decompose Agent | Issue analysis, spec emission, acceptance criteria | direct |
| Mason | Build Agent | Plan execution, property test generation, code generation | react |
| Ranger | Search Agent | Read-only search, output always Warden-scanned | react |
| Arbiter | Triage Agent | Clarifies ambiguous requests, delegates to specialists | delegate |

Each agent carries:
- `agent.yaml` — name, description, tools, skills, trust tier, delegation mode
- `SOUL.md` — system prompt / personality
- `RULES.md` — hard constraints (optional)
- `skills/` — SKILL.md files (optional)

**Consumer renames:** Turing might call Artificer "Tess's Hands". Conductor might call it "Project Builder". The code is the same — only the YAML changes.

---

## Builder Pipeline — Full Sub-Agent Architecture

```
                         Master Orchestrator
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              Super Planner   Progress   Security
              (decompose      Monitor    Scanner
               + order +      (tracks    (runs
               + parallel     XP,        Warden on
                groups)       coverage,  all output)
                              blockers)
                    │
        ┌───────────┼───────────┐───────────┐
        ▼           ▼           ▼           ▼
   Spec Writer   Test Writer  Contract    Plan
   (emits specs  (generates   Verifier    Executor
    + ACs +      property     (checks     (runs
    invariants)  tests from   protocols   phases:
                 invariants)  impl'd)     code→check
                                          →fix→commit)
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   Code Writer   Reviewer    Security
   (implements   (reviews     Scanner
    from spec    progress,    (Warden +
    + tests)     suggests     Sentinel on
                 fixes)       all output)
```

### Builder Roles (from Stronghold)

| Role | What It Does | Source |
|------|-------------|--------|
| **Frank** (Decompose) | Analyzes issues, emits Specs with ACs + invariants | `builders/spec_emitter.py` + `agents/frank/` |
| **Mason** (Build) | Executes plan phases: code generation, test gen, fixes | `agents/mason/` + `builders/runtime.py` |
| **Auditor** (Review) | PR review, mock detection, spec coverage, security | `agents/auditor/checks.py` + `builders/spec_coverage.py` + `builders/verifier.py` |
| **Quartermaster** (Spec) | Template matching — reuses verified specs for similar issues | `builders/spec_templates.py` |
| **Archie** (Property Gen) | Generates Hypothesis property tests from spec invariants | `builders/property_gen.py` |

### Builder Pipeline Stages

```
issue_analyzed → acceptance_defined → tests_written →
implementation_started → implementation_ready → quality_checks_passed → completed
                                                     ↕ (can loop back)
```

### Master Orchestrator + Super Planner

New components for `maistro-core/orchestrator/`:

| Component | Role |
|-----------|------|
| **Master Orchestrator** | Top-level coordinator. Accepts a consolidation plan (or any complex task), breaks it into work items, dispatches to builder roles, tracks progress, handles failures/retries. Manages the global stage machine. |
| **Super Planner** | Decomposes a high-level goal into parallel-safe work groups. Each group contains ordered tasks with dependencies. Groups that don't depend on each other run concurrently. Produces a `ConsolidationPlan` that the Master Orchestrator executes. |
| **Progress Monitor** | Tracks XP earned, spec coverage %, test pass rates, blockers. Reports to Master Orchestrator for adaptive re-planning. |
| **Security Scanner** | Runs Warden + Sentinel on all builder output before acceptance. Gates every stage transition. |

---

## Parallel Execution Plan — Tranche Map

### Group A: Foundation (sequential prerequisite for all groups)

| ID | Task | From | To | Depends | Agent |
|----|------|------|----|---------|-------|
| A1 | Port protocols + types | Stronghold `protocols/`, `types/` | `maistro/protocols/`, `maistro/types/` | — | Mason |
| A2 | Port DI container pattern | Stronghold `container.py` | `maistro/container.py` | A1 | Mason |
| A3 | Port config loader | Stronghold `config/` | `maistro/config/` | A1 | Mason |

### Group B: Memory (parallel after A)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| B1 | Port types/memory.py (Learning, EpisodicMemory, MemoryScope) | Stronghold | A1 | Mason |
| B2 | Port memory/scopes.py | Stronghold | A1 | Mason |
| B3 | Port memory/learnings/{store,extractor,promoter} | Stronghold | B1 | Mason |
| B4 | Port memory/episodic/{store,tiers,retrieval} | Stronghold | B1, B2 | Mason |
| B5 | Port memory/outcomes.py | Stronghold | B1 | Mason |
| B6 | Port persistence/pg_learnings, pg_outcomes | Stronghold | B3, B4, B5 | Mason |
| B7 | Wire get_engine() + Alembic migrations | ADR-011,012 | B6 | Frank |

### Group C: Security (parallel after A)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| C1 | Port warden/patterns.py | Stronghold | A1 | Mason |
| C2 | Port warden/heuristics.py | Stronghold | C1 | Mason |
| C3 | Port warden/sanitizer.py + flag_response.py | Stronghold | C1 | Mason |
| C4 | Port warden/detector.py | Stronghold | C2, C3 | Mason |
| C5 | Port warden/semantic.py (LLM fallback) | Stronghold | C4 | Mason |
| C6 | Port sentinel/{policy,validator,audit} | Stronghold | A1 | Mason |
| C7 | Port sentinel/pii_filter + token_optimizer | Stronghold | A1 | Mason |
| C8 | Wire security into existing maistro security/ | — | C5, C6, C7 | Frank |

### Group D: Classifier (parallel after A)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| D1 | Port types/intent.py | Stronghold | A1 | Mason |
| D2 | Port classifier/keyword.py | Stronghold | D1 | Mason |
| D3 | Port classifier/llm_fallback.py | Stronghold | D1 | Mason |
| D4 | Port classifier/complexity.py | Stronghold | D1 | Mason |
| D5 | Port classifier/engine.py (3-phase orchestrator) | Stronghold | D2, D3, D4 | Mason |
| D6 | Port classifier/multi_intent.py | Stronghold | D5 | Mason |

### Group E: Router (parallel after A)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| E1 | Port router/scoring.py (pure functions) | Stronghold | A1 | Mason |
| E2 | Port router/scarcity.py | Stronghold | A1 | Mason |
| E3 | Port router/speed.py | Stronghold | A1 | Mason |
| E4 | Port router/filter.py | Stronghold | A1 | Mason |
| E5 | Port router/selector.py (RouterEngine) | Stronghold | E1-E4 | Mason |
| E6 | Port types/model.py (ModelConfig, ProviderConfig) | Stronghold | A1 | Mason |

### Group F: Agents + Strategies (parallel after A)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| F1 | Port agents/base.py (Agent, handle pipeline) | Stronghold | A1 | Mason |
| F2 | Port agents/factory.py (seed from filesystem) | Stronghold | F1 | Mason |
| F3 | Port agents/identity.py | Stronghold | A1 | Mason |
| F4 | Port strategies/{react,plan_execute,direct,delegate}.py | Stronghold | F1 | Mason |
| F5 | Port strategies/builders_learning.py | Stronghold | F4, B3 | Mason |
| F6 | Port strategies/tool_http.py | Stronghold | F4 | Mason |
| F7 | Port agent roster (artificer, scribe, forge, etc.) | Stronghold | F4 | Frank |
| F8 | Create default agent.yaml files for renameable agents | New | F7 | Frank |

### Group G: Builder Pipeline (parallel after A, F)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| G1 | Port builders/contracts.py | Stronghold | A1 | Mason |
| G2 | Port builders/runtime.py | Stronghold | G1, F4 | Mason |
| G3 | Port builders/orchestrator.py (stage machine) | Stronghold | G1 | Mason |
| G4 | Port builders/spec_emitter.py | Stronghold | G1 | Mason |
| G5 | Port builders/spec_templates.py | Stronghold | G1 | Mason |
| G6 | Port builders/property_gen.py | Stronghold | G1 | Mason |
| G7 | Port builders/verifier.py | Stronghold | G1 | Mason |
| G8 | Port builders/spec_coverage.py | Stronghold | G1 | Mason |
| G9 | Port builders/logger.py | Stronghold | G1 | Mason |
| G10 | Port builders/services.py | Stronghold | G1 | Mason |

### Group H: A2A (parallel after A, F)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| H1 | Port a2a/delegate.py | Stronghold | A1 | Mason |
| H2 | Port a2a/lifecycle.py | Stronghold | H1 | Mason |
| H3 | Port a2a/guest_peers.py | Stronghold | H1 | Mason |

### Group I: Skills + Marketplace (parallel after A, C)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| I1 | Port skills/parser.py + security_scan | Stronghold | A1, C5 | Mason |
| I2 | Port skills/registry.py | Stronghold | I1 | Mason |
| I3 | Port skills/catalog.py | Stronghold | I1 | Mason |
| I4 | Port skills/marketplace.py (SSRF-safe) | Stronghold | I1 | Mason |
| I5 | Port skills/forge.py | Stronghold | I1 | Mason |
| I6 | Port skills/canary.py | Stronghold | I1 | Mason |
| I7 | Port skills/fixer.py | Stronghold | I1 | Mason |
| I8 | Port skills/connectors.py | Stronghold | I2 | Mason |
| I9 | Port skills/loader.py | Stronghold | I2 | Mason |
| I10 | Port types/skill.py | Stronghold | A1 | Mason |

### Group J: Master Orchestrator + Super Planner (parallel after A, F, G)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| J1 | Design Master Orchestrator protocol | New | A1 | Frank |
| J2 | Implement Super Planner (plan decomposition) | New | J1, F4 | Mason |
| J3 | Implement Master Orchestrator (dispatch + track) | New | J1, G3 | Mason |
| J4 | Implement Progress Monitor | New | J1 | Mason |
| J5 | Implement Security Scanner gate | New | J1, C5 | Mason |
| J6 | Wire Master Orchestrator into maistro-server API | New | J3 | Frank |

### Group K: Persistence (parallel after B)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| K1 | Port persistence/pg_agents.py | Stronghold | F3, B6 | Mason |
| K2 | Port persistence/pg_learnings.py | Stronghold | B3 | Mason |
| K3 | Port persistence/pg_outcomes.py | Stronghold | B5 | Mason |
| K4 | Port persistence/pg_audit.py | Stronghold | A1 | Mason |
| K5 | Port persistence/pg_sessions.py | Stronghold | A1 | Mason |
| K6 | Port persistence/pg_quota.py | Stronghold | A1 | Mason |
| K7 | Port persistence/pg_prompts.py | Stronghold | A1 | Mason |

### Group L: Integration + Wire Consumers (after all groups)

| ID | Task | From | Depends | Agent |
|----|------|------|---------|-------|
| L1 | Update conductor-router to import maistro-core | — | B,C,D,E,F | Frank |
| L2 | Update Project Turing to import maistro-core + maistro-turing | — | B,C,D,E,F | Frank |
| L3 | Update maistro-server to use all ported subsystems | — | all | Frank |
| L4 | Update ADRs for new layout | — | all | Frank |
| L5 | Write CLAUDE.md for maistro-engine | — | all | Frank |

---

## Parallel Execution Matrix

Groups that can run simultaneously (after their dependencies are met):

```
Wave 0:  [A1, A2, A3]                    ← Foundation (sequential)
Wave 1:  [B1, C1, D1, E1, F1]           ← All start in parallel
Wave 2:  [B2-B5, C2-C7, D2-D6, E2-E6, F2-F8]  ← Subsystem internals
Wave 3:  [B6-B7, G1-G10, H1-H3, I1-I10, K1-K7]  ← Wiring + persistence
Wave 4:  [J1-J6]                          ← Master Orchestrator
Wave 5:  [L1-L5]                          ← Consumer integration
```

Each work item within a wave can be assigned to a **separate sub-agent** running in parallel.
The Master Orchestrator manages the wave transitions and dependency resolution.

---

## Agent Naming Convention

Agents are defined by YAML files in `agents/` directory. Default names:

```yaml
# agents/code/agent.yaml
spec_version: "0.1.0"
name: code                    # Default: "code". Rename freely.
display_name: "Code Agent"    # Human-readable. Rename freely.
description: "Multi-phase engineering specialist"
strategy: plan_execute
tools: [read_file, write_file, run_pytest, run_ruff_check, run_mypy, run_bandit, shell_exec]
trust_tier: t1
```

Turing's version:
```yaml
# agents/tess-hands/agent.yaml
name: tess-hands
display_name: "Tess's Hands"
strategy: plan_execute          # Same strategy, different identity
tools: [read_file, write_file, run_pytest, ...]
```

Consumers override the `agents/` directory path to use their own names.
