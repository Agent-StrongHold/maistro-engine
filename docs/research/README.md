# Pipeline Tools Research

This directory contains reference research for three overlapping pipeline features planned for mAIstro-engine. Each document covers the 5 best-in-class tools for one use case, extracts architectural patterns worth adopting, and maps findings to our existing LiteLLM tier config.

## Research Documents

| File | Feature | Tools Covered |
|---|---|---|
| [01-autonomous-pipeline-tools.md](./01-autonomous-pipeline-tools.md) | Autonomous builders pipeline | SWE-agent, OpenHands, Devin 2.0, AutoCodeRover/Sonar, Agentless |
| [02-spec-driven-pipeline-tools.md](./02-spec-driven-pipeline-tools.md) | Interactive spec-driven pipeline | Cursor, AWS Kiro, Augment Intent, Cline, GitHub Spec Kit |
| [03-agentic-coding-assistants.md](./03-agentic-coding-assistants.md) | Agentic coding assistant | Cline, Aider, Continue.dev, Plandex, Goose (Block) |

## The Three Features (Overlapping)

```
┌─────────────────────────────────────────────────────────────────┐
│  FEATURE 1: Autonomous Builders Pipeline                        │
│  Issue → Plan → Code → Test → Fix → CI-green → PR             │
│  Max autonomy · quality gates at every step · human reviews PR │
├───────────────────────────────┬─────────────────────────────────┤
│  FEATURE 2: Spec-Driven       │  FEATURE 3: Agentic Assistant   │
│  Interactive Pipeline         │  (pair programmer mode)         │
│  Spec → Clarify → Plan →      │  REPL-style · cost-aware LLM    │
│  Implement (human gates)      │  routing · LiteLLM backbone     │
└───────────────────────────────┴─────────────────────────────────┘
```

## Top Patterns to Extract (across all three)

### Universally Applicable

1. **ACI / bounded tool output** (SWE-agent) — every tool returns compact, LM-readable output; never raw filesystem dumps
2. **Architect/Editor model split** (Aider, Devin) — strong reasoning model plans; cheap fast model executes edits
3. **Hierarchical localization** (Agentless, AutoCodeRover) — File → Symbol → Line-range scope narrowing before codegen
4. **Constitution-first context injection** (Spec Kit, Cursor) — persistent project governance doc injected into every agent call
5. **Plan-then-execute hard gate** (Cline, Kiro, Cursor) — planning phase is physically incapable of writing code
6. **Worktree-per-agent isolation** (Cursor, Augment Intent) — each parallel agent in its own git worktree; conflicts resolve at PR time
7. **Population-based repair** (Agentless) — generate N patches in parallel; select by test execution
8. **Reproduction test as oracle** (Agentless) — synthesize a failing test from bug description as ground truth for patch ranking
9. **Event stream logging** (OpenHands) — append-only log of all agent actions for replay and fine-tuning
10. **Proactive human escalation** (Devin) — detect low-confidence; pause rather than hallucinate forward

### LiteLLM-Specific (Feature 3)

See [03-agentic-coding-assistants.md → LiteLLM Patterns](./03-agentic-coding-assistants.md) for:
- Complexity router (maps to our Tier 1–4 config)
- Adaptive router with quality/cost weights
- Provider budget routing
- Fallback chains (rate-limit, context-window, content-policy)
- Semantic caching
- Anthropic prefix caching for large codebase contexts
- Cost tracking via Prometheus + Langfuse

## Mapping to maistro-engine's Existing LiteLLM Config

Our current `litellm_config.yaml` already implements the tier pattern:

```
maistro-tier-1  →  qwen2.5-coder:7b   (Tier 1: Quick / cheap tasks)
maistro-tier-2  →  qwen2.5-coder:32b  (Tier 2: Standard implementation)
maistro-tier-3  →  qwen3-coder:80B    (Tier 3: Complex reasoning)
maistro-tier-4  →  qwen3-coder:80B+   (Tier 4: Max quality)
cloud-sonnet    →  claude-sonnet-4    (Cloud fallback)
cloud-opus      →  claude-opus-4      (Cloud fallback: architecture)
gemini-fallback →  gemini-2.5-pro     (Alternate cloud fallback)
```

This maps directly to the **Architect/Editor split** (Tiers 3-4 as architect, Tiers 1-2 as editor) and the **complexity router** patterns documented in the LiteLLM section.

## SWE-bench Context

For the autonomous pipeline, current (May 2026) SWE-bench Verified scores:

| Approach | Score | Cost/issue |
|---|---|---|
| Sonar Foundation Agent | ~79% | ~$1.98 |
| OpenHands CodeAct 2.1 | ~53–77% | pay-per-token |
| Agentless (Claude 3.5+) | ~41–51% | ~$0.34–0.70 |
| SWE-agent | ~12–65% | pay-per-token |
| AutoCodeRover (original) | ~37% | ~$0.65 |

> Scores shift rapidly with new models. Cross-validate at https://www.swebench.com/

---
*Research date: May 2026. Tools explicitly excluded: Claude Code CLI, GitHub Copilot, OpenAI Codex/Codex CLI.*
