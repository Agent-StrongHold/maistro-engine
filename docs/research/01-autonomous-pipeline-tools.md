# Autonomous Code Pipeline Tools: Reference Guide (2025–2026)

> **mAIstro relevance:** This research informs Feature 1 — the autonomous builders pipeline that takes GitHub issues end-to-end to CI-green PRs with minimal human intervention. Key patterns to extract: ACI tool design, hierarchical localization, population-based repair, inline validation, compound model routing.

> **Scope:** Systems that operate on a codebase with minimal human intervention — breaking down GitHub issues, planning solutions, writing code, running tests, fixing bugs, and iterating until CI passes. Excluded: Claude Code CLI, GitHub Copilot, OpenAI Codex/Codex CLI.

---

## Ranking Summary (SWE-bench Verified, as of early 2026)

| Tool | SWE-bench Verified | Cost/issue | License | Type |
|---|---|---|---|---|
| Sonar Foundation Agent (AutoCodeRover lineage) | 79.2% (Feb 2026 claim) | ~$1.98 | Proprietary (open core) | Hosted/OSS research |
| OpenHands (CodeAct 2.1) | ~53–77% (varies by model) | Pay-per-LLM-token | MIT (core), proprietary (enterprise) | Self-hosted / Cloud |
| Devin 2.0 (Cognition) | Proprietary benchmark claims | $20–$500/mo + ACUs | Proprietary SaaS | Hosted SaaS |
| SWE-agent / mini-SWE-agent | ~12–65% (model-dependent) | Pay-per-LLM-token | MIT | Open source |
| Agentless | ~41–51% (w/ Claude 3.5+) | ~$0.34–$0.70 | MIT | Open source |
| Aider (autonomous scripted mode) | N/A SWE-bench (Polyglot: top-tier) | Pay-per-LLM-token | Apache 2.0 | Open source CLI |

> Note: SWE-bench Verified numbers shift rapidly with new model releases. Cross-validate with [swebench.com](https://www.swebench.com/).

---

## Tool 1: SWE-agent / mini-SWE-agent

**URL:** https://github.com/SWE-agent/SWE-agent  
**Documentation:** https://swe-agent.com  
**Paper:** NeurIPS 2024 — "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering"

### Core Architecture

SWE-agent's defining innovation is the **Agent-Computer Interface (ACI)** — a purpose-built interaction layer between an LLM and a software repository, designed around the cognitive and operational constraints of language models rather than human users.

The system runs inside a **Docker container** with the target repository checked out. The LLM is given a custom shell-like environment with a small set of specialized commands:

- `find_file`, `search_file`, `search_dir` — repository navigation with output truncated to fit context windows
- `open`, `scroll_up`, `scroll_down` — a file viewer with a sliding 100-line window (prevents context overflow)
- `edit <start>:<end>` — line-range replacement editor with an integrated linter that **blocks syntactically invalid edits before they are committed**
- `create`, `write` — file creation
- `bash` — limited shell execution for running tests, compiling, etc.

The key ACI design principles discovered empirically:
- Output verbosity is carefully bounded — every tool returns compact, LM-readable summaries, not raw filesystem dumps
- Syntax feedback is immediate — the linter fires on every edit attempt, not after a test run
- Navigation is persistent state — a "current file + current line" context is maintained across turns

**mini-SWE-agent** (2025, the recommended successor) re-implements the same principles in a dramatically simpler codebase, matching SWE-agent performance while being more hackable. The team describes it as "radically simple."

**Multi-agent extension (Open SWE by LangChain):** A 2025 derivative wraps SWE-agent in a LangGraph multi-agent loop with a dedicated Planner agent (repo research + strategy), a Coder agent (implementation), and a Reviewer agent (runs tests, checks formatting, reflects before PR).

### Key Distinguishing Features

- **ACI concept**: First system to rigorously study and design the LM-code interface as a first-class engineering concern
- **Linter-as-guardrail**: Edits are rejected inline before they corrupt the working tree
- **Configurable via YAML**: Full behavior can be specified in config files — models, tool sets, stopping conditions, output format
- **EnIGMA mode**: Extends ACI to cybersecurity (CTF challenges) with Interactive Agent Tools (IATs) for persistent debugger sessions
- **Trajectory logging**: Every agent decision, tool call, and observation is recorded in structured JSON for analysis and fine-tuning

### Quality Gates & Guardrails

- Inline linter blocks syntactically broken edits
- Configurable max-turn limits and token budgets
- Docker sandbox isolation — agent cannot affect host filesystem
- Test execution feedback loops (agent can run the repo's test suite)
- No automatic push to remote — outputs a patch/diff for human review by default

### GitHub Issues / PRs / CI Integration

- **Input**: Accepts a GitHub issue URL directly; fetches issue body + metadata
- **Output**: Generates a patch (diff) and can optionally open a PR via the GitHub API
- **CI**: Does not natively watch CI results; the agent must explicitly run tests inside the container
- **Batch mode**: `run_batch` command processes a list of issues from a file

### Autonomy Model

- **Default**: Fully autonomous, zero human intervention during a run
- **Human-in-the-loop**: Not built-in for standard runs; intervention requires interrupting the process
- **Configurability**: Turn limits, cost caps, and allowed tool sets are set before the run via YAML config
- **Review gate**: Recommended pattern is agent produces patch → human reviews diff → human merges PR

### Key Patterns for Custom Pipelines

- **ACI design principle**: Custom tools should produce bounded, structured output — never raw file dumps
- **Inline validation loops**: Validate every edit immediately (linter, formatter, type-checker) before proceeding
- **Sliding window file viewer**: Avoid giving the LLM entire large files; expose a windowed view with scroll commands
- **Trajectory-as-training-data**: Record all agent steps in structured format for fine-tuning and debugging
- **Configurable scaffolds in YAML**: Decouple agent behavior from agent code

### Licensing / Cost

- **License**: MIT (fully open source)
- **Cost**: Free to run; you pay only for LLM API tokens (any provider: GPT-4o, Claude, Gemini, local models)
- **Supported models**: Any LiteLLM-compatible model

---

## Tool 2: OpenHands (formerly OpenDevin)

**URL:** https://www.openhands.dev  
**GitHub:** https://github.com/OpenHands/OpenHands  
**Paper:** ICLR 2025 — "OpenHands: An Open Platform for AI Software Developers as Generalist Agents"

### Core Architecture

OpenHands is a **platform**, not just an agent — it provides a modular runtime, multiple agent implementations, and multiple deployment surfaces. The primary agent is **CodeAct**.

**CodeAct design**: Rather than calling structured JSON tools, the agent expresses all actions as **executable Python code** (hence "CodeAct"). This unified action space handles bash commands, file edits, web browsing, API calls, and GitHub operations through the same mechanism — Python execution. Research shows this significantly outperforms JSON-schema tool calling on complex multi-step tasks because the LLM is fluent in Python and can compose arbitrary action sequences.

**Runtime/Sandbox architecture:**
- **V0 (pre-2025)**: Every tool call ran inside a Docker sandbox
- **V1 SDK (Nov 2025)**: Refactored into clean module separation — `agent logic`, `execution environment` (optional Docker sandbox or remote cloud), and `interface layer` (CLI/GUI/REST API) are independently replaceable

**Micro-agents**: Specialized sub-agents handle domain-specific workflows. The GitHub micro-agent handles repository operations, PR creation, branch management, and API token authentication as a first-class concern.

**Event stream architecture**: Agent actions and observations flow through an event bus, enabling replay, debugging, and fine-grained observability.

### Key Distinguishing Features

- **CodeAct unified action space**: Python-as-action-language is more expressive than JSON tool schemas
- **GitHub Actions resolver**: A pre-built GitHub Action that runs OpenHands on issues tagged `fix-me` — fully turnkey for existing repos
- **37% self-generated commits**: OpenHands actively uses itself to develop its own resolver
- **Multiple deployment surfaces**: Local Docker, cloud hosted (openhands.dev), enterprise Kubernetes with SSO/RBAC, SDK for embedding
- **Enterprise integrations**: Slack, Jira, Linear, GitLab

### Quality Gates & Guardrails

- **Docker sandbox** (default): Filesystem, network, and process isolation
- **Agent loop termination conditions**: Configurable max steps, budget limits, stuck-detection
- **Test execution**: Agent runs the repo's test suite and iterates on failures before declaring completion
- **Human confirmation hooks**: GUI and CLI support breakpoints where human can inspect before proceeding
- **PR-based delivery**: All changes are proposed as PRs, never directly pushed to protected branches
- **Enterprise RBAC**: Fine-grained access control on what repos/secrets the agent can reach

### GitHub Issues / PRs / CI Integration

- **GitHub resolver (turnkey)**: Install `openhands-resolver.yml` in `.github/workflows/`, set secrets. Label any issue `fix-me` → agent runs → opens a PR with the fix
- **Programmatic API**: REST API enables triggering agent runs from any CI event (PR comment, issue created, CI failure webhook)
- **CI feedback loop**: Agent reads CI check results and iterates when tests fail

### Autonomy Model

- **Fully autonomous mode**: GitHub resolver runs with zero human interaction; labels an issue, gets a PR
- **Human-in-the-loop mode**: GUI provides a chat interface where users can guide the agent mid-task, approve plans before execution, or inspect changes
- **Autonomy dial**: From "supervised pair programming" (interactive chat) to "lights-out CI agent" (resolver)

### Key Patterns for Custom Pipelines

- **CodeAct pattern**: Use Python execution as the universal action primitive — eliminates the tool-schema mismatch problem
- **Micro-agent specialization**: Decompose tasks into domain specialists (GitHub ops, web search, test runner) orchestrated by a coordinator
- **Event stream architecture**: Log all agent events to an append-only stream for replay, debugging, and async monitoring
- **Label-triggered autonomy**: GitHub label → webhook → agent session → PR is the simplest zero-config pipeline pattern
- **Modular runtime**: Separate agent logic from execution environment to enable testing agent behavior without real infrastructure

### Licensing / Cost

- **License**: MIT for core; enterprise directory has a separate commercial license
- **Self-hosted**: Free (MIT core); you supply LLM API keys
- **Cloud hosted**: Individual plan (pay-per-LLM-token or BYOK), Enterprise (custom pricing)
- **Series A**: $18.8M raised Nov 2025 for enterprise cloud expansion

---

## Tool 3: Devin 2.0 (Cognition AI)

**URL:** https://devin.ai  
**Documentation:** https://docs.devin.ai

### Core Architecture

Devin is a **compound AI system** — not a single LLM but an orchestrated ensemble of specialized models running inside a fully isolated cloud VM:

- **Planner**: A high-reasoning model that reads the issue, indexes the codebase (via DeepWiki), and produces a structured plan with checkpoints
- **Coder**: A code-specialized model trained on large volumes of high-quality code, responsible for implementation
- **Critic**: An adversarial review model that evaluates patches for security vulnerabilities, logic errors, and regressions before execution
- **Browser agent**: A dedicated model for web-based research — documentation lookups, StackOverflow, API references

The entire system runs in an **isolated cloud VM per session** equipped with a shell, a code editor (VSCode-compatible), and a browser. Each Devin instance is stateless between sessions but can be given persistent knowledge via the **Knowledge system** (reusable instruction sets) and **DeepWiki** (auto-generated repo documentation).

**Devin 2.0 (April 2025) key changes:**
- **Agent-native IDE**: An interactive VSCode-like environment where developers can observe Devin's edits in real-time
- **Interactive Planning**: Before execution, Devin surfaces a plan with relevant files and findings for human approval/modification
- **Parallel Devins**: Multiple independent Devin sessions can run simultaneously, each with its own IDE, for concurrent workstreams
- **ACU metering**: Work is billed in "Agent Compute Units" reflecting task complexity and duration

### Key Distinguishing Features

- **DeepWiki**: Automatically generates and refreshes comprehensive architecture documentation for every connected repo
- **Persistent knowledge base**: Reusable instruction sets that survive across sessions (coding style, deploy procedures, team conventions)
- **Parallel execution at scale**: Multiple concurrent agents is a core product feature
- **PR merge rate**: From 34% (2024) to 67% (end of 2025) merge rate on PRs opened by Devin
- **Self-healing sessions**: Devin actively brings humans in when confidence is low rather than silently failing

### Quality Gates & Guardrails

- **Sandboxed VM**: Devin cannot escape its isolated environment
- **Interactive Planning checkpoint**: Developer must approve the plan before Devin executes (configurable)
- **Critic model**: Built-in adversarial review before any patch is finalized
- **CI requirement pattern**: Devin's PRs must pass all CI checks before merge; Devin observes CI results and iterates
- **Audit logs**: Full session logs of every command, diff, and decision for compliance

### GitHub Issues / PRs / CI Integration

- **GitHub OAuth**: Devin gets read/write access to repos, PRs, issues, and Actions workflows
- **Programmatic API (REST)**: Spin up Devin sessions from any event — GitHub webhook, Jira issue, Slack message, CI failure
- **Automatic PR reviews**: Devin can be triggered on PR creation to review and suggest improvements
- **CI feedback**: Devin monitors CI check results after pushing a branch and iterates until green

### Autonomy Model

- **Configurable spectrum**: From fully supervised (review every step via IDE) to background autonomous (notify on completion or blockers)
- **Interactive Planning**: Human approves/modifies the plan before execution begins
- **Proactive escalation**: Devin surfaces blockers to the human rather than getting stuck silently

### Key Patterns for Custom Pipelines

- **Compound model architecture**: Different reasoning profiles for planning vs. coding vs. review — don't use one model for everything
- **Wiki-first context building**: Auto-generate and refresh codebase documentation before each agent session
- **Persistent knowledge injection**: Treat reusable constraints (style guides, deploy procedures, security rules) as first-class system inputs, not prompt text
- **ACU-style metering**: Measure agent work in compute units (not just tokens) to budget complex multi-step tasks
- **Proactive human escalation**: Design agents to detect low-confidence states and pause for human input rather than hallucinating forward

### Licensing / Cost

- **License**: Proprietary SaaS; no open-source components
- **Core plan**: $20/month (~5 ACUs included, additional at $2.25/ACU)
- **Team plan**: $500/month (250 ACUs included, unlimited concurrency)
- **Enterprise**: Custom pricing with Devin API access, SSO, audit logs

---

## Tool 4: AutoCodeRover / Sonar Foundation Agent

**URL (open source):** https://github.com/AutoCodeRoverSG/auto-code-rover  
**Sonar Foundation Agent:** https://github.com/AutoCodeRoverSG/sonar-foundation-agent  
**Paper:** ISSTA 2024 — "AutoCodeRover: Autonomous Program Improvement"

### Core Architecture

AutoCodeRover's foundational insight is that software projects should be treated as **structured programs** (via Abstract Syntax Trees), not flat file collections.

**Original AutoCodeRover (2024) — Two-phase pipeline:**

**Phase 1: Context Retrieval** — 7-tool AST search API:
- `search_class(class_name)` — returns class signature
- `search_method(method_name)` — returns method signature
- `search_code(code_snippet)` — fuzzy code search
- (+ 4 file-scoped variants)

The agent iterates in "strata" — each stratum decides which API calls to make based on accumulated context, avoiding context window overflow through deliberate bounded retrieval.

**Optional SBFL (Spectrum-Based Fault Localization):** Statistical analysis of passing/failing test execution traces assigns suspiciousness scores to methods, giving the LLM a ranked starting point.

**Phase 2: Patch Generation** — with sufficient context, generates a patch, validates against the test suite, and refines if tests fail.

---

**Sonar Foundation Agent (2025) — Evolution:**

After Sonar's acquisition (Feb 2025), rebuilt the architecture:
- **Framework**: LlamaIndex tool-calling agent
- **Toolset (3 tools)**: `bash` (stateful shell), `string_replace_editor` (file manipulation), `ast_symbol_finder` (inherited AST search)
- **"Free workflow" model**: Removed rigid two-stage pipeline; single agent handles all stages in an open loop
- **Extended thinking**: Uses Claude Sonnet 4.5's extended thinking with simplified, test-driven prompts
- **Result**: Workflow redesign alone improved solve rate from ~58% to ~70%

**Performance (Nov 2025):** 75–79.2% SWE-bench Verified, ~$1.26–$1.98/issue, ~10.5 min/issue.

### Key Distinguishing Features

- **AST-based navigation over grep**: Structural search is more precise than text matching
- **Stratified retrieval**: Prevents context window bloat through deliberate bounded, iterative search rounds
- **SBFL integration**: One of the few systems that formally integrates statistical fault localization
- **Free workflow model (v2)**: Single-agent open loop outperforms rigid multi-stage pipelines as LLMs get more capable
- **SonarQube Remediation Agent**: Technology embedded into SonarQube's CI/CD integrations — triggers automatically on Sonar-detected code quality issues

### Quality Gates & Guardrails

- Test suite execution after every patch
- Patch validation loop — agent retries with refined context if tests fail
- Stateful bash execution means build errors are visible and actionable
- SonarQube integration adds static analysis quality gates upstream

### Key Patterns for Custom Pipelines

- **AST-as-index**: Build a structural code index (tree-sitter, jedi, LSP) at pipeline start — enables semantic lookups instead of grep
- **Stratified context retrieval**: Bounded retrieval rounds where each round's output determines the next round's queries
- **SBFL augmentation**: Run test suite diffs to rank suspicious locations before LLM context retrieval
- **Tool reduction**: Fewer, more powerful tools (bash + editor + AST search) outperform large tool menus
- **Extended thinking for hard problems**: Use a reasoning-first model pass for complex logic bugs before switching to a coding model

### Licensing / Cost

- **Original AutoCodeRover**: MIT license (open source, free to self-host)
- **Sonar Foundation Agent**: Apache 2.0 (open source research artifact)
- **LLM cost**: ~$0.65–$1.98 per issue

---

## Tool 5: Agentless

**URL:** https://github.com/OpenAutoCoder/Agentless  
**Paper:** arXiv 2407.01489 — "Agentless: Demystifying LLM-based Software Engineering Agents"

### Core Architecture

Agentless challenges the assumption that autonomous code repair requires an agentic loop with dynamic tool use. Instead, it implements a **deterministic three-phase pipeline** where the LLM's role at each phase is tightly constrained — no free-form tool calling, no agent planning.

**Phase 1: Hierarchical Localization**

1. **File-level**: LLM reads issue + condensed repo structure → ranked list of suspicious files
2. **Class/function-level**: LLM reads suspicious files → `file::function` targets
3. **Edit location**: LLM reads specific functions → exact line ranges

**Phase 2: Patch Generation**

For each edit location, **sample N candidate patches** (typically 10–20) in unified diff format using temperature > 0 to create a diverse patch population. Embarrassingly parallel — all candidates generated simultaneously.

**Phase 3: Patch Validation & Ranking**

1. Select relevant regression tests from the test suite (keyword/semantic matching against bug description)
2. Generate a **reproduction test** that should fail on buggy code and pass on the fix
3. Run all candidates through regression tests + reproduction test
4. Rank by: (a) passing reproduction test, (b) passing all regression tests, (c) patch size (prefer minimal)
5. Select highest-ranked patch

### Key Distinguishing Features

- **No agent loop**: LLM never decides what to do next — pipeline structure is fixed. Deterministic, reproducible, debuggable.
- **Population-based repair**: Generating N diverse patches and selecting by test results is more reliable than iterative single-patch refinement
- **Reproduction test generation**: Automatically synthesizes a test capturing the bug as ground truth oracle for patch ranking
- **Cost efficiency**: ~$0.34 per issue at initial publication
- **Interpretability**: Every decision point is auditable

### Quality Gates & Guardrails

- Hierarchical localization prevents the LLM from seeing irrelevant code (bounded context)
- Reproduction test acts as a formal oracle — patches that don't fix the bug are automatically rejected
- Regression test suite run ensures no regressions are introduced
- Ranking function is deterministic and transparent
- No iterative agent loop means no risk of the agent taking destructive actions or getting stuck in loops

### Key Patterns for Custom Pipelines

- **Population-based repair**: Generate N patches in parallel (with temperature diversity) and select by test execution
- **Hierarchical localization as a general pattern**: File → symbol → line-range is reusable for any code modification task
- **Reproduction test as oracle**: Synthesize a failing test from the bug description before generating fixes
- **Constrained LLM roles**: Give the LLM a highly specific, bounded role at each pipeline stage — more reliable and cheaper
- **Regression test selection**: Keyword/semantic matching of issue description against test names cheaply selects the right tests

### Licensing / Cost

- **License**: MIT (open source)
- **Cost**: ~$0.34–$0.70 per issue
- **Supported models**: Any OpenAI-compatible API; best results with Claude 3.5 Sonnet (~40–51% SWE-bench Verified)

---

## Honorable Mention: Aider (Autonomous Scripted Mode)

**URL:** https://aider.chat | **License:** Apache 2.0

Aider is primarily an interactive CLI pair-programmer, but its scripting features make it viable for pipeline automation:

```bash
aider \
  --model claude-sonnet-4-5 \
  --message "Fix the bug described in issue #123: $(gh issue view 123 --json body -q .body)" \
  --yes-always \
  --auto-commits \
  --no-stream \
  src/affected_file.py tests/test_affected.py
```

**Key autonomous-mode flags:**
- `--message` / `-m`: Single instruction, process, exit (disables interactive chat)
- `--yes-always`: Auto-confirm all prompts
- `--auto-commits`: Commit every change with auto-generated Conventional Commits message
- `--dry-run`: Generate changes without writing (for preview/review pipelines)

**Architect mode for complex tasks:** Pairs a reasoning model (o3, Claude Opus) as "architect" with a faster editing model (GPT-4o, Sonnet) as "editor."

---

## Cross-Cutting Patterns Summary

| Pattern | Source Tool | Description |
|---|---|---|
| ACI (Agent-Computer Interface) | SWE-agent | Design tools specifically for LM consumption: bounded output, immediate validation feedback |
| CodeAct (Python as universal action) | OpenHands | Use Python execution as the single action primitive |
| Hierarchical localization | Agentless, AutoCodeRover | File → symbol → line-range scope narrowing before any codegen |
| Population-based repair | Agentless | Generate N diverse patches, select by test execution |
| AST-indexed search | AutoCodeRover, Sonar | Structural code index at startup; semantic lookups over file scanning |
| Stratified retrieval | AutoCodeRover | Bounded context retrieval rounds prevent context window overflow |
| SBFL augmentation | AutoCodeRover | Statistical fault localization from test runs cheaply ranks suspicious locations |
| Reproduction test synthesis | Agentless | Auto-generate a failing test from bug description as oracle for patch validation |
| Inline validation | SWE-agent | Validate every edit immediately (lint, format, typecheck) before proceeding |
| Compound model routing | Devin, Aider architect mode | Route planning, coding, and review to specialized models |
| Wiki-first context | Devin | Pre-generate and refresh repo documentation before agent sessions |
| Event stream logging | OpenHands | Append-only event log of all agent actions for replay, debugging, fine-tuning |
| Label-triggered autonomy | OpenHands | GitHub label → webhook → agent session → PR |
| Proactive human escalation | Devin | Detect low-confidence states; pause for human input rather than hallucinating |
| Free workflow over rigid pipelines | Sonar Foundation Agent | Once LLMs are capable, open-loop single-agent beats multi-stage constrained pipelines |

### Quality Gate Checklist for Any Pipeline

1. **Pre-edit**: Syntax/lint validation before any file write
2. **Post-edit**: Reproduction test (synthesized from bug description)
3. **Post-edit**: Regression test suite (selected by semantic matching to issue)
4. **Pre-PR**: CI must be green before PR is opened
5. **Pre-merge**: Human review gate (branch protection rules)
6. **Audit**: Full structured log of every agent action, tool call, and observation

---

*Sources: SWE-agent (NeurIPS 2024), OpenHands (ICLR 2025, github.com/OpenHands/OpenHands), Devin 2.0 (cognition.ai/blog/devin-2), AutoCodeRover (ISSTA 2024, github.com/AutoCodeRoverSG), Sonar Foundation Agent (sonarsource.com/blog/introducing-sonar-foundation-agent), Agentless (arXiv 2407.01489, github.com/OpenAutoCoder/Agentless), Aider (aider.chat). SWE-bench leaderboard: swebench.com*
