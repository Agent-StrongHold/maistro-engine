# mAIstro vs OpenClaw: Gap Analysis

## Context

OpenClaw (125k+ GitHub stars) follows a philosophy that a proper AI agent needs five
core primitives: **Soul, Memory, Context, Heartbeat, and Taskmaster**. Without them,
your bot is essentially a ChatGPT wrapper — it takes input, calls an LLM, returns
output, and forgets everything.

This document analyzes what mAIstro is missing relative to that framework.

---

## The Five Core Primitives

### 1. Soul (Identity / Personality) — MISSING

**OpenClaw**: Every agent has a `SOUL.md` file defining who it is, how it behaves,
what it values. The personality evolves over time. The agent knows who it is across
sessions.

**mAIstro**: The conductor has a static system prompt in `agents/prompts.py`. No
persistent identity, no evolving personality, no values system. Every task gets the
same generic engineering assistant prompt.

**To fix**: Add a workspace-level `SOUL.md` (or equivalent config) that defines agent
identity and gets injected into every LLM call. Allow it to evolve based on
interactions.

### 2. Memory — SCHEMA EXISTS, NOT WIRED

**OpenClaw**: Multi-layered memory system:
- `MEMORY.md` — long-term memory (persists across months)
- `memory/YYYY-MM-DD.md` — daily conversation logs
- `USER.md` — profile of the human being helped
- All just files. Git-versionable. Human-readable.

**mAIstro**: `MemoryEntry` table with pgvector embeddings defined in
`memory/store.py`. `KnowledgeNode` table for dependency graphs. Both are **completely
unused** in Phase 1. Every task starts from zero context.

**To fix**: Wire up the existing `MemoryEntry` and `KnowledgeNode` schemas. At
minimum, persist task results and conversation summaries. Inject relevant memories
into the conductor prompt before each task.

### 3. Context (Workspace Awareness) — MINIMAL

**OpenClaw**: Before every action, the agent loads: SOUL.md + USER.md + recent memory
+ AGENTS.md (operating manual) + relevant skills. Full workspace context on every
turn.

**mAIstro**: Single system prompt per task. The conductor gets task description +
constraints + workspace path. No accumulated context, no user profile, no awareness
of previous work in the same workspace.

**To fix**: Build a context assembly step that runs before each LLM call. Gather:
agent identity, user profile, recent memory, workspace state (recent git log, file
structure), and relevant knowledge nodes.

### 4. Heartbeat (Proactive Autonomy) — EMPTY MODULE

**OpenClaw**: Wakes up every 30 minutes. Runs a context guard + memory health check.
Can proactively act — remind you about things, clean up memory, flag issues.
`HEARTBEAT.md` defines what to check.

**mAIstro**: The `scheduler/` module exists but is empty. The agent only acts when
explicitly given a task via the API. Zero proactive behavior.

**To fix**: Implement a periodic heartbeat that:
- Checks workspace health (stale branches, failing CI, orphaned containers)
- Summarizes and compacts daily memory
- Runs any user-defined periodic checks
- Can be configured per-workspace via a `HEARTBEAT.md` equivalent

### 5. Taskmaster (Skill System / Composability) — HARDCODED

**OpenClaw**: 5,400+ skills in a registry. Skills are markdown-first (`SKILL.md`).
Runtime discovery — the agent finds relevant skills per turn. Selective injection to
avoid prompt bloat.

**mAIstro**: 5 hardcoded agent roles. Only the conductor works. Tools are FastMCP
endpoints defined in Python. Adding a capability requires writing code, rebuilding,
and redeploying.

**To fix**: Create a skill/plugin system where capabilities are defined as markdown +
optional scripts. Allow runtime discovery. Selectively inject relevant skills per
task.

---

## Architectural Gaps

| Feature | OpenClaw | mAIstro |
|---------|----------|---------|
| **Gateway (always-on)** | Single control plane for sessions, channels, tools, events. Stays running. | REST API + WebSocket. No persistent sessions. |
| **Multi-channel** | 50+ channels (WhatsApp, Telegram, Slack, Discord, Signal, etc.) | Chat completions endpoint + GitHub webhooks |
| **State as files** | `~/.openclaw/workspace/` — git-versionable, human-editable | In-memory queue (lost on restart) or unused Postgres |
| **Agent loop** | receive → route → context + LLM + tools → stream → persist | Single-pass: task in → LLM call → result out |
| **Multi-agent** | Many agents per gateway, each with own workspace/tools/permissions | 5 roles defined, only conductor works |
| **Skill composability** | Markdown-first, runtime discovery, selective injection | Hardcoded FastMCP endpoints |

---

## What mAIstro Does Better

| Feature | mAIstro Advantage |
|---------|-------------------|
| **Sandboxed execution** | Docker containers with resource limits, network isolation, TTL cleanup. OpenClaw doesn't have built-in sandboxing. |
| **Security primitives** | 38 dangerous command patterns, 32+ injection detection patterns, trust boundaries, secret comparison. |
| **Compute tiers** | 4-tier model system (quick/standard/thorough/ultra) with circuit breakers, retry logic, cost/quality tradeoffs. |
| **Software engineering focus** | Git operations, PR creation, CI webhooks, code review pipeline. Purpose-built for code tasks. |
| **Observability** | Langfuse tracing, Prometheus metrics, structured logging (skeleton ready). |

---

## Priority Remediation

### Phase 1: Wire What Exists (Low effort, high impact)
1. **Connect memory store** — The Postgres schemas are defined. Wire them up.
2. **Persist task results** — Store completed task summaries as memory entries.
3. **Context assembly** — Before each conductor call, inject recent memories + workspace state.

### Phase 2: Add Missing Primitives (Medium effort)
4. **Soul file** — Add per-workspace identity config that gets injected into prompts.
5. **User profile** — Track who is making requests and their preferences.
6. **Heartbeat** — Implement the scheduler with periodic workspace health checks.

### Phase 3: Extensibility (Higher effort)
7. **Skill system** — Markdown-first skill definitions with runtime discovery.
8. **Multi-agent routing** — Wire up planner/coder/reviewer as separate agents.
9. **Channel integrations** — Add at least Slack/Discord as input channels.

---

## Conclusion

mAIstro is a well-architected **task execution engine**. OpenClaw is an **agent
runtime**. The difference is that OpenClaw agents have identity, remember you, act on
their own, and live across sessions.

The irony is that mAIstro already has half the infrastructure designed (memory
schemas, knowledge graphs, scheduler module) — it's just not connected. The path
forward isn't to become OpenClaw; it's to wire up what's already there and add the
missing primitives that turn a task executor into a proper agent.

OpenClaw's core insight applies: **a personal AI agent is a gateway problem, not a
model problem.** mAIstro currently treats the model as the product. It should treat
the model as a component of a larger persistent system.
