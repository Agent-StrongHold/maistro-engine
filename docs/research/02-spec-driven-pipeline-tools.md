# Interactive Spec-Driven Feature Pipeline Tools: Reference Guide (2025–2026)

> **mAIstro relevance:** This research informs Feature 2 — the interactive spec-driven pipeline that delivers features with structured human checkpoints. Key patterns to extract: constitution-first governance, EARS notation for requirements, plan-then-execute hard gate, artifact traceability chain, resumable workflow YAML with pause gates.

> **Scope:** Systems where a human provides a spec/PRD/feature description and the tool interactively refines, plans, and implements through a structured pipeline with human checkpoints. Excluded: Claude Code CLI, GitHub Copilot, OpenAI Codex/Codex CLI.

---

## Tool 1: Cursor (Agent Mode / Background Agents)

**URL:** https://cursor.com

### Core Architecture

Cursor 2.0/3.x implements a multi-layer agent architecture on top of a VS Code fork. The primary unit is the **Composer/Agent**, which receives high-level task descriptions and executes them using a mixture-of-experts model called Composer — trained via reinforcement learning directly inside real codebases.

**Background Agents** run in isolated Ubuntu VMs with internet access. Each agent gets a separate git worktree (linked to the same repo but on its own branch), which prevents file conflicts and allows up to 8 parallel agents to work concurrently without stepping on each other. Agents automatically create PRs upon completion for human review.

### Spec Ingestion Model

Specs enter through the **Chat/Composer panel** as natural language. The recommended pattern:

1. Paste a PRD, feature description, or failing-test definition into the composer
2. Optionally attach files via `@file` references or `@codebase` for semantic retrieval
3. The agent generates an **implementation plan** before touching any code — this plan is the first human checkpoint
4. Cursor 3 introduced **steering documents** (`.cursor/rules` files) that function as persistent project-level context injected into every agent invocation

### Pipeline Stages

| Stage | Mechanism |
|---|---|
| 1. Task intake | Natural language in Composer panel; `@file` or `@codebase` for context |
| 2. Plan generation | Agent proposes implementation plan; developer reviews before execution |
| 3. Implementation | Agent uses file editing, terminal, web search, MCP tools; up to 25 tool calls per burst |
| 4. Verification | Agent auto-runs tests and linters; shows results in terminal panel |
| 5. Review | Full cross-file diff review before changes are applied |
| 6. Branch / PR | Background agents create PRs automatically for human merge decision |

### Human-in-the-Loop Checkpoints

- **Plan approval gate:** Execution is blocked until developer approves the implementation plan
- **25-tool-call limit:** Agents pause after 25 tool calls and surface a "Continue" button
- **Terminal command preview:** Commands shown before execution
- **Full diff review:** Cross-file unified diff presented before any file changes are applied
- **PR review:** Background agents create PRs; merge requires human approval

### Quality Gates & Guardrails

- Automated test execution post-modification
- Automatic linting and error checking within the implementation loop
- Git worktree isolation prevents agents from corrupting the main branch

### Key Patterns Worth Extracting

- **Steering document pattern:** Project-level `.cursor/rules` files inject persistent architectural context into every agent call — equivalent to a system prompt for your codebase
- **Worktree isolation per agent:** Each parallel agent operates in its own branch/worktree; merge conflicts handled at PR time
- **Test-first grounding:** Feeding failing tests as the spec reduces hallucination significantly
- **Plan-then-execute checkpoint:** Mandatory human gate between plan generation and code execution

### Licensing / Cost

- **Hobby:** Free (limited agent requests)
- **Pro:** $20/month — frontier model access, ~225 Sonnet-equivalent requests
- **Ultra:** $200/month — 20x usage, priority features
- **Teams:** $40/user/month — shared rules, centralized billing, SSO, RBAC
- Proprietary

---

## Tool 2: AWS Kiro (Agentic Spec-Driven IDE)

**URL:** https://kiro.dev

### Core Architecture

Kiro was launched by AWS at re:Invent 2025 as a purpose-built spec-driven agentic IDE, built on Code OSS (the open-source VS Code base). It inverts the standard coding assistant model: **the spec is the primary artifact; generated code is treated as a build output** that must continuously conform to the spec.

Under the hood, Kiro routes between **Claude Sonnet** for reasoning-heavy spec generation and **Amazon Nova** for high-throughput code generation, using AWS Bedrock as the unified model gateway.

**Agent Hooks** are event-driven automations that trigger on file system events: on file save, on file create/delete, on PR open, on custom manual trigger. They function like CI pipeline steps embedded directly in the IDE.

### Spec Ingestion Model

Kiro's spec ingestion is the most formalized of any tool in this list. A single natural language prompt triggers a three-phase structured artifact generation pipeline:

**Phase 1 — Requirements Document:** Decomposes the prompt into user stories expressed in **EARS (Easy Approach to Requirements Syntax)** notation, which enforces explicit acceptance criteria including edge cases.

> Format: "When [trigger], the system shall [response], so that [rationale]."

**Phase 2 — Design Document:** Technical architecture artifacts: data flow diagrams, TypeScript interfaces, database schemas, API endpoint contracts, sequence diagrams, and testing strategy — all anchored to Phase 1 requirements.

**Phase 3 — Tasks Document:** Discrete implementation tasks with dependency graph analysis. Kiro identifies which tasks are independent and groups them into concurrent "waves" for parallel execution.

Spec files live in the project repository, making them version-controllable and reviewable in PRs alongside code.

### Pipeline Stages

| Stage | Mechanism |
|---|---|
| 1. Prompt intake | Natural language; multimodal (UI mockups, video screen recordings) |
| 2. Requirements generation | EARS-notation user stories with acceptance criteria; human reviews and approves |
| 3. Design generation | Technical architecture anchored to approved requirements; human reviews |
| 4. Task generation | Dependency-aware task list with parallelization hints; human reviews |
| 5. Implementation (waves) | Tasks execute in parallel waves respecting dependency graph |
| 6. Hook-triggered automation | File-save/event hooks run tests, update docs, scan for credentials |

**Workflow variants:**
- **Requirements-First:** Full three-phase pipeline with approval between phases (default)
- **Design-First:** Start from a technical design and generate requirements backward
- **Quick Plan:** Auto-generate all artifacts without approval gates
- **Bugfix Spec:** Structured bug analysis mode with current/expected behavior comparison

### Human-in-the-Loop Checkpoints

- **Between each spec phase:** Three mandatory approval gates before a single line of code is written
- **Task-level execution:** Individual tasks can be reviewed and modified before execution
- **Hook approval:** Manual-trigger hooks require explicit invocation

### Quality Gates & Guardrails

- EARS notation enforces completeness — acceptance criteria must be explicit and measurable
- Design phase generates test strategy before implementation begins (test-first by default)
- Agent hooks run automatic security credential scanning before commits
- Architecture enforcement hooks fire on file save
- Spec-code drift detection: Kiro can detect when code diverges from the spec and flag it
- Task dependencies prevent implementation before prerequisites are verified complete

### Key Patterns Worth Extracting

- **EARS notation for requirements:** Forces every requirement to have explicit trigger, response, and rationale fields
- **Three-artifact spec structure:** Requirements + Design + Tasks as separate documents, each reviewed independently
- **Event-driven hook system:** File system events as automation triggers embedded directly into the development loop
- **Dependency-wave task execution:** Analyzing task dependencies before execution and batching independent tasks into parallel waves
- **Spec as version-controlled artifact:** Checking spec files into the repo alongside code makes requirements reviewable in PRs

### Licensing / Cost

- **Free:** 50 credits (perpetual)
- **Pro:** $20/month — 1,000 credits
- **Power:** $200/month — 10,000 credits
- Proprietary; built on open-source Code OSS

---

## Tool 3: Augment Code Intent (Multi-Agent Orchestration Workspace)

**URL:** https://www.augmentcode.com/product/intent

### Core Architecture

Intent is a standalone macOS desktop application (Windows on roadmap) launched in public beta in February 2026. It is purpose-built for spec-driven multi-agent orchestration at the team and enterprise scale.

The orchestration model uses a **three-tier agent system** with six named specialist agent types:

1. **Coordinator Agent:** Understands the task via the Context Engine, proposes a plan as a spec. Execution blocked until human approves.
2. **Implementor Agents (Specialist Pool):** Execute in parallel "waves" after coordinator approval. Six named specialists: Investigate, Implement, Verify, Critique, Debug, Code Review. Each agent receives only the context it actually needs.
3. **Verifier Agent:** Validates all results against the living spec, flags inconsistencies, bugs, or missing pieces.

**Context Engine:** Processes codebases across 400,000+ files through semantic dependency analysis. For a given task, curates from 4,456+ potential context sources down to ~682 highly relevant items. Precision context rather than brute-force full-repo dumps.

**Git Worktree Isolation:** Each workspace is backed by its own git worktree. State persists across session closures (resumable sessions).

**BYOA (Bring Your Own Agent):** Supports Claude Code, OpenAI Codex, and OpenCode as backend execution agents.

### Spec Ingestion Model

Intent uses a **living spec** model — the spec document is not a static input but an evolving artifact that agents update as they make progress:

1. User writes an initial spec (or Intent helps generate one)
2. Coordinator Agent reads the spec + Context Engine output and proposes a refined plan as a spec update
3. Human reviews and approves the plan before any code execution begins
4. As Implementors complete tasks, they update the spec to reflect actual implementation decisions
5. Spec changes automatically propagate context to active agents
6. Verifier checks final outputs against current spec state

### Key Patterns Worth Extracting

- **Living spec as synchronization bus:** The spec is a shared mutable document all agents read from and write to. Solves the "plan drift" problem.
- **Specialist agent pool pattern:** Named specialists (Investigate, Implement, Verify, Critique, Debug, Review) each with narrow scope and appropriate context
- **Precision context curation:** Semantic dependency analysis curates the specific 682/4456 relevant items. Reduces hallucination and cost.
- **Two-gate minimum pattern:** Coordinator approval + Verifier gate = two mandatory human checkpoints bookending every implementation wave
- **Worktree-per-agent isolation:** The only safe way to run parallel agents on the same repo

### Licensing / Cost

- **Public beta pricing (May 2026):** $20/month (Indie) to $200/month (Max); Enterprise at custom pricing
- **BYOA option:** Users who bring their own Claude Code/Codex subscriptions; Context Engine requires a paid Intent plan
- Proprietary SaaS

---

## Tool 4: Cline (VS Code Agent — Plan/Act Model)

**URL:** https://cline.bot | https://github.com/cline/cline

### Core Architecture

Cline is an open-source VS Code extension (Apache 2.0) operating as a model-agnostic coding agent. It supports any LLM provider through bring-your-own-API-key.

The core architectural pattern is **Plan/Act mode separation** — a hard state toggle:

- **Plan Mode:** Read-only. Cline can read files, run searches, analyze the codebase, ask clarifying questions, and propose implementation strategies. Cannot modify files or execute commands.
- **Act Mode:** Read/write. Cline implements based on the plan. Each file modification and terminal command requires explicit per-step human approval.

**Cline cannot switch from Plan to Act autonomously** — only the developer can trigger the transition. This is the fundamental safety invariant.

**Checkpoint system:** A shadow Git repository runs alongside the project, capturing file snapshots after each tool use. Three restore modes: Restore Files, Restore Task Only, Restore Files & Task.

### Pipeline Stages

| Stage | Mechanism |
|---|---|
| 1. Spec intake | Paste PRD or `@file` reference; optionally attach architecture docs |
| 2. Plan mode | Cline reads codebase, asks clarifying questions, proposes implementation strategy; read-only |
| 3. Human approval gate | Developer reviews plan, iterates if needed, explicitly switches to Act mode |
| 4. Act mode (per-step) | Each file edit and terminal command surfaces for approve/reject; full diff shown |
| 5. Checkpoint capture | Shadow git repo captures snapshot after each approved tool call |
| 6. Testing | Cline runs tests via terminal; results fed back into context |
| 7. Review / rollback | Compare any checkpoint, diff, or restore to any prior snapshot |

### Human-in-the-Loop Checkpoints

- **Plan-to-Act mode switch:** Cline cannot self-promote from Plan to Act — developer must explicitly toggle
- **Per-tool-call approval:** Every file write, terminal command, and browser action requires explicit approve/reject
- **Diff preview:** Each file modification shows the full proposed diff before it is applied
- **Checkpoint restore:** Developer can restore to any prior checkpoint state at any point

### Quality Gates & Guardrails

- Hard read-only constraint in Plan mode prevents accidental modification before the plan is approved
- Per-step approval gates — no multi-file change batch applied without human review of each step
- Shadow git checkpoint system enables instant rollback without affecting the project's actual git history
- MCP Marketplace integration allows plugging in external quality tools as MCP servers

### Key Patterns Worth Extracting

- **Hard read/write mode separation:** Making the planning state physically incapable of writing code is a stronger safety guarantee than a soft "don't write yet" instruction
- **Per-step approval with diff preview:** Approval at the granularity of individual tool calls gives maximum human control
- **Shadow git checkpoint pattern:** Parallel git repo for checkpoints without polluting the project's actual commit history
- **`.clinerules` project context files:** Persistent project-level context injection that survives across sessions
- **Deep planning command:** A dedicated "explore the entire blast radius before writing" mode for large features

### Licensing / Cost

- **License:** Apache 2.0 (open source) — free to use
- **Model cost:** BYOK — you pay only for LLM inference. Typical range: $15–$120/month
- **Cline Teams:** $20/user/month; first 10 seats always free

---

## Tool 5: GitHub Spec Kit (Agent-Agnostic Scaffolding Toolkit)

**URL:** https://github.com/github/spec-kit

### Core Architecture

GitHub Spec Kit is not itself an AI coding agent but a **scaffolding layer and workflow framework** that makes any AI coding agent operate in a spec-driven pipeline. Open-sourced by GitHub in September 2025 (MIT license).

The toolkit is a Python CLI (`specify-cli`) that:
1. Generates and manages structured spec artifact files in a `.specify/` directory tree
2. Installs slash commands (or agent-native skills) into supported AI coding agents
3. Enforces a sequential workflow where each phase must complete before the next is available
4. Provides a template/preset/extension system for customizing every phase

**30+ supported agent integrations:** GitHub Copilot, Claude Code, Cursor, Google Gemini CLI, Qwen CLI, Tabnine, Goose, Mistral, OpenCode, Kiro, Pi, Forge, and more.

**Extension ecosystem:** 120+ community extensions for integration (Jira, Azure DevOps, GitHub Projects, Confluence, Linear), quality gates (CI Guard, MAQA CI/CD Gate, security review, drift detection), and code review.

### Spec Ingestion Model

**`/speckit.constitution`:** Synthesizes existing project documentation into a `constitution.md` — the permanent governing principles document. Written once, evolves with the project.

**`/speckit.specify`:** Takes natural language feature description and generates a structured `spec.md` containing prioritized user stories with acceptance criteria. The spec is **tool-agnostic** — it describes *what*, not *how*.

**`/speckit.clarify`:** Structured ambiguity resolution before planning. Generates specific questions organized by category (error handling, edge cases, performance) and waits for answers.

### The 8-Phase Pipeline

| Phase | Command | Output Artifact | Human Gate |
|---|---|---|---|
| 1. Governance | `/speckit.constitution` | `.specify/memory/constitution.md` | Initial review |
| 2. Specification | `/speckit.specify` | `.specify/specs/{ID}/spec.md` | Explicit review required |
| 3. Clarification | `/speckit.clarify` | Updated `spec.md` with resolved ambiguities | Q&A session |
| 4. Planning | `/speckit.plan` | `plan.md`, `research.md`, `data-model.md` | Explicit review required |
| 5. Consistency check | `/speckit.analyze` | Analysis report (read-only, no files modified) | Review analysis |
| 6. Task breakdown | `/speckit.tasks` | `tasks.md` with dependencies and parallel markers | Review task list |
| 7. Issue tracking | `/speckit.taskstoissues` | GitHub Issues created from tasks | Optional |
| 8. Implementation | `/speckit.implement` | Code changes, task by task | Per-task review |

**Artifact file structure:**
```
.specify/
  memory/constitution.md
  specs/{FEATURE_ID}/
    spec.md       # functional requirements
    plan.md       # technical implementation strategy
    tasks.md      # task breakdown with dependencies
    research.md   # research findings from plan phase
    data-model.md # schemas and interfaces
```

### Human-in-the-Loop Checkpoints

- **Post-specify review:** Documented mandatory review gate before clarification
- **Clarification Q&A:** Interactive structured questioning with developer answering each identified ambiguity
- **Post-plan review:** Technical architecture and research reviewed before task decomposition
- **Post-analyze review:** Consistency analysis report reviewed before implementation
- **Workflow YAML pause gates:** Explicit `pause` directives in workflow YAML files that halt automation pipelines pending human review

### Key Patterns Worth Extracting

- **Constitution-first governance:** A persistent governing document that all agents must align to, written before any feature work
- **What-before-how requirement separation:** The spec phase is explicitly forbidden from specifying technology choices
- **Structured clarification before planning:** A full pipeline phase dedicated to ambiguity resolution before any technical design work
- **Artifact traceability chain:** Vision → Constitution → Spec → Plan → Research → Tasks → Implementation
- **Agent-agnostic scaffolding layer:** The framework constrains how any agent behaves by giving it structured templates and required artifact structure
- **Deferred-decision documentation:** Instead of blocking on unknowns, document them with their planned resolution point
- **Resumable workflow YAML:** YAML-defined pipelines with explicit pause gates — automation handles mechanical work while humans handle judgment calls

### Licensing / Cost

- **MIT License** — completely open source
- **CLI tool** (`specify-cli`) — free, Python 3.11+, installable via `uv tool install` or `pipx`
- **Cost:** Zero for the framework; pay only for LLM inference through whatever agent you use
- **Enterprise/offline:** Offline wheel bundles available for air-gapped installations

---

## Comparative Summary

| Dimension | Cursor | AWS Kiro | Augment Intent | Cline | GitHub Spec Kit |
|---|---|---|---|---|---|
| **Category** | IDE agent | Spec-driven IDE | Orchestration workspace | VS Code agent | Framework/scaffolding layer |
| **Spec formalism** | Steering docs + prose | EARS notation (3-phase) | Living spec document | `.clinerules` + prose | Structured markdown artifacts |
| **Spec-to-plan gate** | Yes | Yes (3 separate approvals) | Yes (coordinator approval) | Yes (Plan mode → Act switch) | Yes (per-command review) |
| **Multi-agent** | Up to 8 parallel | Wave-based parallel tasks | 6 specialist agents | Single agent | Depends on underlying agent |
| **Worktree isolation** | Yes (per background agent) | Task-level dependency waves | Yes (per workspace) | No | No (depends on agent) |
| **Rollback mechanism** | Diff review + PR | Spec-phase rollback | Git integration | Shadow git checkpoints | Git-based |
| **Agent flexibility** | Cursor models only | Claude Sonnet + Nova Bedrock | BYOA (Claude/Codex/OpenCode) | Any LLM provider | Any of 30+ agents |
| **Open source** | No | No | No | Yes (Apache 2.0) | Yes (MIT) |
| **Entry price** | Free (limited) | Free (50 credits) | Free (beta credits) | Free (BYOK) | Free (MIT) |

## Cross-Cutting Patterns

1. **Constitution-first context injection** — Project governance doc encoding architecture, standards, and tech stack, injected into every agent invocation automatically
2. **Hard separation of planning from execution** — Plan generation is physically incapable of modifying code
3. **What-before-how requirement decomposition** — Spec phase describes behavior; Plan phase describes implementation
4. **Structured ambiguity resolution before planning** — Dedicated clarification phase with explicit questions from the spec
5. **Artifact traceability chain** — Every task traces to a plan item; every plan item to a spec requirement
6. **Worktree-per-agent isolation** — Each parallel agent in its own git worktree; conflicts resolve at PR time
7. **Precision context curation** — Semantic dependency analysis curates the 10–20% of files relevant to the specific task
8. **Two-gate minimum** — Plan approval gate + verifier check = two mandatory human checkpoints
9. **Executable test specs** — Providing failing tests as the primary spec gives an unambiguous, machine-verifiable definition of done
10. **Resumable, pausable pipeline state** — Pipeline state persists across human review cycles

---

*Sources: cursor.com, kiro.dev, augmentcode.com/product/intent, cline.bot, github.com/github/spec-kit, github.github.com/spec-kit. Research date: May 2026.*
