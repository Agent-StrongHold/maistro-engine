# Agentic Coding Assistant Tools: Reference Guide (2025–2026)

> **mAIstro relevance:** This research informs Feature 3 — the interactive coding assistant mode built on mAIstro's existing LiteLLM cost-aware routing. Key patterns: Architect/Editor model split (maps directly to our Tier 3-4 as architect, Tier 1-2 as editor), system message tools for model-agnostic agent mode, shadow git checkpoints, LiteLLM complexity router wired to our tier config.

> **Scope:** Developer-facing tools with a pair-programmer feel, multi-step agentic execution, multi-LLM backend support, and cost-aware model selection. Excluded: Claude Code CLI, GitHub Copilot, OpenAI Codex/Codex CLI.

---

## Tool 1: Cline

**URL:** https://cline.bot / https://github.com/cline/cline  
**License:** Apache 2.0

### Core Architecture

Cline is a VS Code extension (TypeScript) that runs as a sidebar agent. It operates on a human-in-the-loop model: every file change and terminal command requires explicit user approval before execution. State management includes workspace checkpoints for rollback.

**Plan/Act modes:** Plan mode is a non-destructive reasoning phase with no file writes. Act mode executes the plan. Plan mode is also cheaper since it uses fewer tokens on average.

**Context management:** Cline selectively includes file information rather than dumping entire trees into the token window. As of v3.78 (April 2026), a hard "Spend Limit Reached" UI stops runaway agents. Per-session token limits (e.g., 50K tokens) are configurable.

### LLM Routing / Multi-Model Support

Provider list crossed 30 in 2026: Anthropic, OpenAI, Google Gemini, AWS Bedrock, Azure OpenAI, Google Vertex, OpenRouter, Cerebras, DeepSeek, Moonshot, Alibaba Qwen, xAI Grok, Mistral, Groq, Fireworks, Together, SambaNova, Nebius, HuggingFace, local models via Ollama or LM Studio, custom OpenAI-compatible base URLs.

Cline natively supports custom base URLs and API keys, making it fully compatible with any OpenAI-compatible gateway (e.g., LiteLLM proxy). Router-based cost cutting (cheap models for classification, frontier for synthesis) can reduce costs 50%+ when combined with a gateway.

### Cost Awareness Features

- Real-time token count and estimated USD cost displayed per interaction
- Cumulative cost tracking across the entire task loop
- Configurable per-session token spend limits
- "Spend Limit Reached" UI guard (v3.78+)
- Dedicated Usage Analytics section in settings (token consumption + cost history)
- BYOK: users pay provider directly, no Cline markup

### Agentic Capabilities

| Capability | Support |
|---|---|
| File create/edit | Yes (with diff review) |
| Terminal command execution | Yes (with approval) |
| Browser (headless) | Yes (screenshots, interactive testing) |
| MCP tool use | Yes (MCP Marketplace since v3.4, Feb 2025) |
| Linter/test output monitoring | Yes |
| Workspace checkpoints/rollback | Yes |
| Subagent spawning | Via MCP |

### Key Patterns for mAIstro

- **Human-in-the-loop approval model** — fine-grained permission prompts before any destructive action
- **Plan mode as a cheap reasoning pass** — send the plan request to Tier 1 or 2; only invoke Tier 3-4 for Act mode
- **Custom base URL + OpenAI-compatible API** — point at our LiteLLM proxy without any Cline-specific changes
- **MCP Marketplace** — extend the agent with custom tools (databases, CI systems) without forking the codebase
- **Checkpoint system** — git-like rollback for agentic changes; useful for reviewing multi-file refactors

### Licensing / Cost

- **License:** Apache 2.0 — free to use
- **Cost:** BYOK — pay API costs directly
- **Cline Teams** (2026): $20/user/month; first 10 seats always free

---

## Tool 2: Aider

**URL:** https://aider.chat  
**License:** Apache 2.0

### Core Architecture

Aider is a terminal-based AI pair programmer. It operates within a git repository and automatically stages and commits AI-generated changes with descriptive commit messages. The architecture centers on a **repo map** (tree-sitter-based symbol extraction across the entire codebase) that lets the LLM understand project structure without loading all files into context.

The defining architectural pattern is the **Architect/Editor dual-model split**:

1. **Architect model** (strong reasoning model, e.g., o1, DeepSeek R1, Claude Opus): receives the task and produces a high-level solution proposal in prose
2. **Editor model** (fast, code-focused model, e.g., GPT-4o, Claude Sonnet, DeepSeek Chat): receives the architect's plan and produces concrete file editing instructions
3. **Weak model:** A third, cheapest model used for low-value tasks like commit message generation

This decoupling means expensive reasoning models are only used for thinking, not for formatting diffs.

**Benchmark result (2025):** DeepSeek R1 (architect) + Claude Sonnet (editor) = 64.0% on aider polyglot benchmark at **14x less cost** than the previous o1 SOTA.

### LLM Routing / Multi-Model Support

- Supports 100+ LLMs via litellm under the hood
- Native support: OpenAI, Anthropic, Google Gemini, DeepSeek, Groq, Mistral, Cohere, Ollama, LM Studio, any OpenAI-compatible endpoint
- Three simultaneous model slots: architect (`--model`), editor (`--editor-model`), weak (`--weak-model`)
- Runtime model switching: `/model`, `/editor-model`, `/weak-model` chat commands

### Cost Awareness Features

- Explicit three-tier model budget control: expensive architect, mid-tier editor, cheap weak model
- Prompt caching supported for Anthropic (Claude Sonnet, Haiku) and DeepSeek
- Manual context control: add only files you want to edit (`/add <file>`)
- Real-time cost display per request in the terminal
- `/tokens` command shows current context token usage

### Agentic Capabilities

| Capability | Support |
|---|---|
| File create/edit | Yes (multiple edit formats) |
| Terminal command execution | Yes (`--auto-test`, `--auto-lint`) |
| Git integration | Deep — auto-commit, diff review, `--dry-run` |
| Voice input | Yes |
| Image/URL context | Yes |
| Auto-test/lint loop | Yes (runs tests, fixes failures autonomously) |

### Key Patterns for mAIstro

- **Architect/Editor split pattern** — maps directly to our tier config: **Tier 3-4** (qwen3-coder 80B) as architect, **Tier 1-2** (qwen2.5-coder 7B-32B) as editor
- **Edit format as a routing concern** — different models perform best with different edit formats (whole-file, diff, SEARCH/REPLACE)
- **Repo map + selective file loading** — tree-sitter symbol extraction creates a compact project index; cap token budget without sacrificing project awareness
- **Prompt caching for codebase context** — on Anthropic models, prefix the repo map and system files with a cache-control header
- **`--weak-model` pattern** — delegate cheap/repetitive tasks (commit messages, short summaries) to Tier 1

### Licensing / Cost

- **License:** Apache 2.0 (open source)
- **Cost:** Free. Typical: $0.01–$0.10 per feature implementation with GPT-4o; significantly less with DeepSeek or local models

---

## Tool 3: Continue.dev

**URL:** https://www.continue.dev / https://docs.continue.dev  
**License:** Apache 2.0

### Core Architecture

Continue is an open-source IDE extension for VS Code and JetBrains that acts as a configurable AI coding assistant. Its architecture is built around **model roles**: different models are assigned to different tasks (chat, autocomplete, edit, apply, embed, rerank, summarize).

The agent mode uses an innovative **system message tools** approach: tool calls are serialized as XML in the system message rather than using native function calling APIs. This ensures agent mode works consistently across all models regardless of whether they natively support tool use.

### LLM Routing / Multi-Model Support

Model routing is **role-based and explicit** in `config.yaml`:

```yaml
models:
  - name: Claude Opus for Chat
    provider: anthropic
    model: claude-opus-4-5
    roles: [chat, edit, apply]

  - name: Codestral Autocomplete
    provider: mistral
    model: codestral-latest
    roles: [autocomplete]

  - name: Nomic Embed
    provider: ollama
    model: nomic-embed-text
    roles: [embed]
```

**LiteLLM integration:** Continue supports LiteLLM as a provider via `apiBase` pointing to a LiteLLM proxy server:

```yaml
models:
  - name: LiteLLM Router
    provider: openai
    model: maistro-tier-2          # model name as defined in our litellm_config.yaml
    apiBase: http://localhost:4000
    apiKey: your-litellm-key
    roles: [chat, edit]
```

Supported providers natively: OpenAI, Anthropic, Azure, Google (Gemini/Vertex), Mistral, Ollama, LM Studio, DeepSeek, Together, Groq, Cohere, Voyage, AWS Bedrock, HuggingFace, and any OpenAI-compatible endpoint.

**Recommended models by role (2025–2026):**
- Agent/Plan: Claude Opus 4.1, Claude Sonnet 4.6, Gemini 2.5 Pro, Qwen3 Coder 480B (open), Devstral 27B (open)
- Autocomplete: QwenCoder 2.5, Codestral, Mercury Coder
- Embedding: Nomic Embed Text, Voyage Code 3

### Cost Awareness Features

- Role-based model assignment: expensive frontier model only used for chat/edit; cheap model for autocomplete (high-frequency, low-value)
- Per-model `contextLength` and `maxTokens` limits in config
- LiteLLM proxy integration offloads all cost tracking, budgeting, and provider budget routing to the gateway layer
- Local/offline model support via Ollama eliminates API costs entirely for autocomplete

### Key Patterns for mAIstro

- **System message tools pattern** — converting tool schemas to XML in the system prompt enables agent mode on any LLM, including models that don't natively support function calling. Critical for local Qwen models.
- **Role-based model routing** — explicit mapping of `roles: [autocomplete]` to cheap/fast models and `roles: [chat, edit]` to frontier models is the simplest cost optimization
- **`apiBase` as LiteLLM gateway hook** — any Continue-compatible model can be routed through our LiteLLM proxy by setting `apiBase` to `http://localhost:4000`
- **Workspace-level config overrides** — `.continuerc.json` with `mergeBehavior: merge` allows project-specific model preferences

### Licensing / Cost

- **License:** Apache 2.0 (open source)
- **Cost:** Free extension. Users pay provider API costs.

---

## Tool 4: Plandex

**URL:** https://plandex.ai / https://github.com/plandex-ai/plandex  
**License:** AGPL-3.0

### Core Architecture

Plandex is a terminal-based AI coding agent written in Go, designed specifically for **large codebases and multi-step tasks**. Its core architectural differentiator is a sophisticated context management system that scales to projects too large to fit in any single context window.

**Key architectural components:**

1. **Tree-sitter project maps** — symbol-level indexes (functions, classes, variables) generated for 30+ languages
2. **Automatic context loading (v2 default)** — on plan creation, project map + user prompt → LLM selects relevant files before planning
3. **Smart context window management (v2)** — a sliding context window that grows and shrinks per implementation step. Only files relevant to the current step are loaded.
4. **Diff sandbox** — all AI-generated changes are staged in an in-memory sandbox. Changes are reviewed as a unified diff before any file is written.
5. **Multi-model plan execution** — different models handle different phases (planning, implementation, debugging, summarization)

**Context capacity:** 2M token effective context window with default model pack; tree-sitter indexes can cover directories with 20M+ tokens.

**Cloud wind-down:** Plandex Cloud shut down November 7, 2025. The project is now entirely self-hosted + BYOK.

### LLM Routing / Multi-Model Support

- Supports Anthropic, OpenAI, Google, and open-source providers
- Built-in Ollama support added in v2.2.0
- Custom model configuration with per-role model assignment (planning model, implementation model, summarization model, weak model)
- Model packs: pre-defined combinations of models optimized for different cost/quality trade-offs

### Cost Awareness Features

- **Context caching** across the board for OpenAI, Anthropic, and Google models
- **Smart context window management** — loads only necessary files per step
- **Tree-sitter project maps** — compact structural representation dramatically reduces tokens for project-awareness queries
- Model packs allow selecting cheaper vs. more capable model combinations globally

### Key Patterns for mAIstro

- **Sliding context window pattern** — dynamically determine per-step which files are relevant and load only those. Implementable in any agentic system with a planning phase.
- **Diff sandbox before write** — never write to the filesystem until the full diff has been reviewed
- **Tree-sitter project map as a context budget optimization** — a 500-token project map can replace 50,000 tokens of full file content for the "what exists where" query
- **Context caching on prefix** — when the same system prompt + project map appears at the start of every request, Anthropic/OpenAI prompt caching makes all subsequent steps pay only for the delta
- **Multi-phase model routing** — planning (Tier 3-4) → implementation (Tier 2) → summarization (Tier 1). Maps directly onto our LiteLLM tier config.

### Licensing / Cost

- **License:** AGPL-3.0 (open source, self-host)
- **Cost:** Free (self-hosted). Plandex Cloud discontinued November 2025.

---

## Tool 5: Goose (Block / AAIF)

**URL:** https://block.xyz/goose / https://github.com/block/goose  
**License:** Apache 2.0

### Core Architecture

Goose is a general-purpose on-machine AI agent (not purely a coding tool) written in Rust (48.7% Rust, 45.7% TypeScript). It runs as a native desktop app (macOS, Linux, Windows), a full-featured CLI, and an embeddable API server (`goose serve`). In December 2025, Block contributed Goose to the Linux Foundation's **Agentic AI Foundation (AAIF)**.

**Core agent loop:** Thought → Plan → Act → Observe (recursive, with configurable autonomy levels).

**Extension system:** 70+ extensions via the Model Context Protocol (MCP). The MCP ecosystem covers developer tools (GitHub, VS Code, Docker), productivity suites (Google Drive, Asana, Slack), and specialized services (Kubernetes, databases, CI/CD).

**Lead/Worker model:** Goose's primary cost-routing mechanism. A frontier "Lead" model handles high-level reasoning and planning; a faster, cheaper "Worker" model handles repetitive execution tasks. Configurable per-session.

### LLM Routing / Multi-Model Support

15+ providers supported natively: Anthropic, OpenAI, Google (Gemini), Ollama, OpenRouter, Azure, AWS Bedrock, and more.

**Lead/Worker split:** assign different models to the Lead (reasoning) and Worker (execution) roles.

**Mid-session model switching** (key differentiator): Goose allows switching models mid-project/session without losing context, enabling "start with cheap model, escalate to frontier when stuck" workflows.

### Cost Awareness Features

- **Lead/Worker pattern** — high-precision frontier model only for complex reasoning; cheaper open-weight model for repetitive execution tasks
- **Local model support** — route to Ollama/local models for zero API cost on appropriate tasks (maps to our `maistro-tier-1/2` config)
- **OpenRouter integration** — single API key, model selection, and cost tracking across 100+ models
- Egress logging inspector (2026) for auditing token usage and costs per session

### Key Patterns for mAIstro

- **Lead/Worker model split** — the Goose equivalent of Aider's Architect/Editor pattern. Route tasks through a cheap fast model by default, escalate to expensive frontier model only when the worker returns low-confidence or stuck signals.
- **Mid-session model switching** — switching models without losing context is valuable in long-running tasks where complexity varies
- **`fast_model` configuration** — declarative assignment of a secondary fast model for latency-sensitive sub-tasks
- **AGENTS.md** — codebase-specific instruction files (analogous to CLAUDE.md) that inject project conventions into every session
- **Subagent parallelism** — spawn independent context windows for parallel tasks (code review + implementation + documentation simultaneously)

### Licensing / Cost

- **License:** Apache 2.0 (open source)
- **Cost:** Free. Users pay provider API costs (BYOK).

---

## Honorable Mention: Amp (Sourcegraph)

**URL:** https://ampcode.com

Notable for its pricing model innovation:

- **Smart mode** — state-of-the-art model (Claude Opus 4.7), unconstrained, maximum capability
- **Rush mode** — faster, cheaper, for small well-defined tasks
- **Deep mode** — extended reasoning (GPT-5.5), for genuinely complex architectural problems

The three-mode system maps directly onto a three-tier LiteLLM routing strategy and provides a developer-facing UX for cost-vs-capability trade-offs.

**Cost model:** Zero markup on provider API pricing; $10 free credits. Team plan: at-cost pricing. Enterprise: 50% markup, $1,000 minimum.

---

## LiteLLM Patterns for Cost-Aware Routing

> This section directly applies to our existing `litellm_config.yaml` which already has `maistro-tier-1` through `maistro-tier-4` plus cloud fallbacks.

### Pattern 1: Tier-Based Routing (Complexity Router)

Maps to our existing tier config. Route requests to different model tiers based on estimated task complexity:

```yaml
# Add to litellm_config.yaml
model_list:
  # ... existing tier definitions ...

  # The complexity router virtual model
  - model_name: maistro-auto
    litellm_params:
      model: auto_router/complexity_router
    complexity_router_config:
      simple_model: maistro-tier-1       # Quick / cheap tasks
      medium_model: maistro-tier-2       # Standard implementation
      complex_model: maistro-tier-3      # Complex reasoning
      reasoning_model: cloud-opus        # Architecture decisions (cloud fallback)
      tier_boundaries:
        simple_max_complexity: 0.3
        medium_max_complexity: 0.6
        complex_max_complexity: 0.85
```

### Pattern 2: Adaptive Router (Cost + Quality Aware)

For workloads where you want the router to learn over time which model performs best per task type:

```yaml
model_list:
  - model_name: adaptive-coding-router
    litellm_params:
      model: auto_router/adaptive_router
    adaptive_router_config:
      available_models: ["maistro-tier-1", "maistro-tier-2", "maistro-tier-3", "cloud-sonnet"]
      weights:
        quality: 0.6   # lean toward quality for coding tasks
        cost: 0.4
```

**Weight presets for coding agent use cases:**

| Use case | quality | cost |
|---|---|---|
| Autocomplete / quick edit | 0.3 | 0.7 |
| Standard feature implementation | 0.6 | 0.4 |
| Architecture review / refactor | 0.8 | 0.2 |
| Security audit / complex reasoning | 0.95 | 0.05 |

### Pattern 3: Provider Budget Routing

Prevent cost overruns at the provider level:

```yaml
# Add to litellm_config.yaml
router_settings:
  provider_budget_config:
    anthropic:
      budget_limit: 50.00   # USD
      time_period: 1d
    openai:
      budget_limit: 30.00
      time_period: 1d

litellm_settings:
  success_callback: ["prometheus"]
```

Time period formats: `"30s"`, `"10m"`, `"24h"`, `"1d"`, `"1mo"`

### Pattern 4: Fallback Chains

Three fallback types with different trigger conditions:

```yaml
litellm_settings:
  num_retries: 3
  request_timeout: 300   # our local models can be slow

  # General fallbacks (rate limits, 5xx errors, timeouts)
  fallbacks:
    - "maistro-tier-3": ["maistro-tier-4", "cloud-sonnet"]
    - "maistro-tier-4": ["cloud-sonnet", "cloud-opus"]
    - "cloud-sonnet":   ["cloud-opus", "gemini-fallback"]

  # Context window fallbacks (prompt too long for primary model)
  context_window_fallbacks:
    - "maistro-tier-2": ["maistro-tier-3", "cloud-sonnet"]

  allowed_fails: 3
  cooldown_time: 60

router_settings:
  enable_pre_call_checks: true   # check context length BEFORE sending
```

### Pattern 5: Caching Strategies

**Redis exact-match cache (production standard):**

```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: redis://localhost:6379
    ttl: 3600
    cache_tool_calls: true
```

**Semantic cache (fuzzy matching for similar prompts):**

```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis-semantic
    host: redis://localhost:6379
    similarity_threshold: 0.90
    redis_semantic_cache_embedding_model: "text-embedding-ada-002"
    ttl: 7200
```

**Anthropic prompt caching (prefix caching for large static context):**

```python
# Pass cache_control on the large static parts of your prompt
response = litellm.completion(
    model="anthropic/claude-sonnet-4-6",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": large_codebase_context,
                    "cache_control": {"type": "ephemeral"}  # cache this prefix
                },
                {
                    "type": "text",
                    "text": user_question   # this part varies; not cached
                }
            ]
        }
    ]
)
```

Anthropics charges `cache_creation_input_tokens` at write time, then `cache_read_input_tokens` (discounted ~90%) on subsequent calls. For a 50K-token codebase context reused across 10 requests, the savings are ~9x on those tokens.

### Combining Patterns: Reference Architecture for maistro Coding Agent

```
User request
     │
     ▼
[LiteLLM Proxy :4000]
     │
     ├─ Check semantic cache → return if hit (saves 100% cost)
     │
     ├─ Complexity Router classifies task
     │     SIMPLE  → maistro-tier-1  (qwen2.5-coder:7b, fastest)
     │     MEDIUM  → maistro-tier-2  (qwen2.5-coder:32b)
     │     COMPLEX → maistro-tier-3  (qwen3-coder 80B, temperature 0.3)
     │     REASON  → maistro-tier-4  (qwen3-coder 80B, large ctx)
     │     CLOUD   → cloud-sonnet    (if local fails / budget allows)
     │
     ├─ Provider budget check → skip exhausted cloud providers
     │
     ├─ Send to selected model (with Anthropic prefix caching on cloud calls)
     │
     ├─ On failure: fallback chain → retry → cooldown → next tier
     │
     └─ Log cost to Prometheus / Langfuse
```

This architecture can reduce costs 60–85% vs always using a frontier model, while maintaining frontier-model quality for the tasks that actually require it. For our primarily local setup (Ollama P40), the cost savings apply to cloud spillover calls.

---

## Quick Comparison Matrix

| Tool | Paradigm | LLM Routing | Cost Features | Agentic Depth | IDE Integration | License |
|---|---|---|---|---|---|---|
| **Cline** | IDE extension (VS Code) | Manual + gateway-compatible | Per-session token limits, BYOK, spend cap | Deep (file, terminal, browser, MCP) | VS Code, JetBrains, Cursor, Windsurf | Apache 2.0 |
| **Aider** | Terminal | Architect/Editor/Weak 3-tier | Prompt caching, selective file loading | Deep (file, terminal, git) | Terminal (any) | Apache 2.0 |
| **Continue.dev** | IDE extension (VS Code + JetBrains) | Role-based explicit YAML | Role routing (autocomplete=cheap, chat=frontier), LiteLLM proxy | Moderate (file, terminal, MCP) | VS Code, JetBrains | Apache 2.0 |
| **Plandex** | Terminal | Multi-phase plan models | Sliding context window, prompt caching, tree-sitter maps | Deep (file, terminal, build/test debug) | Terminal (any) | AGPL-3.0 |
| **Goose** | Desktop app + CLI + API | Lead/Worker, fast_model, mid-session switch | Lead/Worker split, local model routing, OpenRouter | Deep (file, terminal, browser, parallel subagents) | Desktop app, terminal | Apache 2.0 |

---

*Sources: cline.bot, aider.chat, docs.continue.dev, plandex.ai, block.xyz/goose, ampcode.com, docs.litellm.ai. Research date: May 2026.*
