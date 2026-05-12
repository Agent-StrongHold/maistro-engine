# Hive Conductor — Product Specification

**Product**: Hive Conductor — Multi-agent AI platform
**Distribution**: curl installer + web wizard → docker compose up
**Date**: 2026-05-12
**Status**: Design phase

---

## Install Experience

### Option A: Curl one-liner (CLI users)

```bash
curl -fsSL https://get.hiveconductor.com | bash
```

The installer:
1. Detects OS (Linux, macOS, WSL2)
2. Checks for Docker — installs via official convenience script if missing
3. Checks for Docker Compose — installs if missing
4. Creates `~/hive-conductor/` with docker-compose.yml, .env, config.yaml
5. Pulls pre-built images from GHCR
6. Starts the stack
7. Prints: "Hive Conductor is running! Open http://localhost:8101"

### Option B: Web install wizard (everyone else)

1. Visit `https://install.hiveconductor.com`
2. System check — "We'll install Docker if you don't have it"
3. API keys — Paste Anthropic/Google/OpenAI keys (or "I'll configure later")
4. Model selection — Pick 2-3 models from curated list with cost/quality info
5. Optional extras — Home Assistant URL? Turing personality? CLI-Anything?
6. "Copy this command and paste it in your terminal" — generates curl one-liner with choices baked in

### Distribution URLs

| URL | What |
|---|---|
| `get.hiveconductor.com/install.sh` | Curl installer target |
| `releases.hiveconductor.com/` | docker-compose.yml + versioned compose files |
| `ghcr.io/blakematthews-dev/hive-conductor` | Container images |
| `install.hiveconductor.com` | Web wizard (static site) |

---

## Services

| Service | Port | Purpose |
|---|---|---|
| hive-conductor | 8101 | FastAPI app + React SPA (all UI) |
| postgres | 5432 | Persistence |
| redis | 6379 | Sessions + caching + task queue |
| litellm | 4000 | Model gateway (or bring your own) |
| langfuse | 3100 | Observability (optional) |
| mcp-sandbox | — | Code execution MCP server |
| mcp-git | — | Git/GitHub MCP server |
| mcp-browser | — | Browser automation MCP server |
| mcp-ha | — | Home Assistant MCP server (optional) |

---

## Pages and Endpoints

### Page: Chat (`/`)

Real-time conversation with the agent swarm. OpenAI-compatible.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/chat/completions` | POST | Send message, get response (streaming or non-streaming) |
| `/v1/models` | GET | List available models with tiers |
| `/v1/sessions` | GET | List conversation sessions |
| `/v1/sessions/{id}` | GET | Get session history |
| `/v1/sessions/{id}` | DELETE | Delete session |

Features:
- SSE streaming responses (OpenAI chunk format)
- Tool call visualization (expandable panels showing tool name, args, result)
- Agent/model/intent badges on each response
- Clarification UI (CLARIFY verdict presents inline options for user to pick)
- Security alert banners (Gate blocks with strike count and escalation ladder)
- Session history sidebar with search
- Model selector in input bar
- Quick action suggestion cards on empty state (4 suggested tasks)
- New chat button (creates fresh session)
- Markdown rendering with syntax highlighting, LaTeX math, tables

---

### Page: Missions (`/missions`)

Async task management with clarification loops and progress tracking.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/tasks` | POST | Submit new mission |
| `/v1/tasks` | GET | List missions (paginated, filterable by status) |
| `/v1/tasks/{id}` | GET | Get mission detail + progress |
| `/v1/tasks/{id}` | DELETE | Cancel mission |
| `/v1/tasks/{id}/updates` | POST | Send user update/guidance to running mission |
| `/v1/tasks/{id}/updates` | GET | Get update thread |
| `/v1/tasks/{id}/clarify` | POST | Answer clarification question |
| `/v1/tasks/{id}/result` | GET | Get final result |

Mission lifecycle:
```
SUBMITTED → CLARIFYING → RUNNING → COMPLETE
                      └→ BLOCKED (security)
                      └→ FAILED
```

Features:
- Two-panel layout: mission list (left) + mission detail (right)
- Clarification loop: agent asks question, user answers inline, mission continues
- Progress timeline (vertical): classified → dispatched → tool calls → results
- Update thread: back-and-forth between user and agent during execution
- Mission creation form: title, description, priority (P0-P5), agent preference, workspace path
- Status badges with colors per lifecycle state (SUBMITTED=grey pulsing, CLARIFYING=amber pulsing, RUNNING=phosphor spinning, COMPLETE=phosphor solid, BLOCKED=burn, FAILED=burn)
- Filter by status, agent, date range
- Manual trigger: run a mission immediately

---

### Page: Schedules and Triggers (`/schedules`)

Cron-based recurring tasks and event-driven triggers.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/schedules` | POST | Create scheduled task |
| `/v1/schedules` | GET | List schedules |
| `/v1/schedules/{id}` | GET | Get schedule detail |
| `/v1/schedules/{id}` | PUT | Update schedule |
| `/v1/schedules/{id}` | DELETE | Delete schedule |
| `/v1/schedules/{id}/run` | POST | Trigger immediate run |
| `/v1/schedules/{id}/history` | GET | Past executions |
| `/v1/triggers` | GET | List registered triggers |
| `/v1/triggers/{id}` | PUT | Enable/disable trigger |
| `/v1/triggers/{id}/history` | GET | Trigger fire history |
| `/v1/events/emit` | POST | Emit custom event |
| `/v1/events/triggers` | GET | List event trigger definitions |

Features:
- Three tabs: Schedules | Triggers | History
- Cron editor with visual "next 5 run times" preview and human-readable conversion
- Schedule cards: name, cron, agent, prompt, last run, next run, enabled toggle, run-now button
- Trigger builder with three modes:
  - INTERVAL: every N seconds/minutes/hours (with jitter option)
  - EVENT: regex pattern on event name (e.g., `security\.warden\.block`)
  - STATE: poll condition (e.g., "quota > 80%")
- Circuit breaker status per trigger (active / tripped / cooldown)
- Execution history table: trigger/schedule, timestamp, status, duration, result preview
- Maximum 10 schedules per user (enforced by scheduling store)
- 15-minute minimum interval on cron expressions

---

### Page: Skills (`/skills`)

Skill marketplace, AI-assisted builder, import with security scanning.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/skills` | GET | List installed skills |
| `/v1/skills` | POST | Create/import skill |
| `/v1/skills/{name}` | GET | Get skill detail |
| `/v1/skills/{name}` | PUT | Update skill |
| `/v1/skills/{name}` | DELETE | Delete skill |
| `/v1/skills/scan` | POST | Security scan a skill definition |
| `/v1/skills/forge` | POST | AI-assisted skill generation |
| `/v1/skills/marketplace` | GET | Browse marketplace |
| `/v1/skills/import` | POST | Import from URL or file upload |

Features:
- Three tabs: Installed | Marketplace | Builder
- Skill cards: name, description (2 lines), trust tier badge, usage count, last used, active toggle
- Trust tier badges: Skull (unusable, new) → T3 (sandboxed, read-only) → T2 (community-approved) → T1 (operator-vetted) → T0 (built-in)
- AI Builder wizard:
  1. Describe: "What should this skill do?" (free text)
  2. Generate: AI drafts SKILL.md with triggers, conditions, actions
  3. Review: Show generated skill with syntax highlighting
  4. Security Scan: Warden scans generated skill, show findings
  5. Save: Install at Skull trust tier (promoted after operator review)
- Import flow:
  1. Source: upload file, paste URL, or paste YAML directly
  2. Security scan runs automatically (Warden + Sentinel validation)
  3. Results panel: findings list with severity (critical/warning/info)
  4. Critical findings = "Cannot import" with explanation
  5. Warnings only = "Import with warnings" option
  6. Clean = "Install" button
- Skill editing: inline YAML editor
- Export: download SKILL.md

---

### Page: Agents (`/agents`)

Agent roster, AI-assisted builder, import with security scanning.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/agents` | GET | List active agents |
| `/v1/agents` | POST | Create/import agent |
| `/v1/agents/{name}` | GET | Get agent detail (config + SOUL + RULES) |
| `/v1/agents/{name}` | PUT | Update agent |
| `/v1/agents/{name}` | DELETE | Delete agent |
| `/v1/agents/{name}/scan` | POST | Security scan agent definition |
| `/v1/agents/forge` | POST | AI-assisted agent generation |
| `/v1/agents/intents` | GET | Get intent→agent mapping table |

Features:
- Three tabs: Active | Templates | Builder (same pattern as Skills)
- Agent cards: name, strategy (react/plan_execute/direct/delegate), model, SOUL excerpt, trust tier
- Strategy selector: visual cards for each strategy with description
- AI Builder: describe agent role → generates YAML + SOUL.md + RULES.md → Warden scan → save
- Import: upload bundle → scan → install
- Inline editing: YAML editor for config, markdown editor for SOUL.md and RULES.md
- Personality radar chart (HEXACO-24 visual, if Turing enabled)
- Intent mapping table: which agent handles which task type (task_type → agent_name grid)

---

### Page: MCP Servers (`/mcp`)

MCP server management, discovery, import with security scanning.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/mcp/servers` | GET | List connected MCP servers |
| `/v1/mcp/servers` | POST | Add MCP server (URL) |
| `/v1/mcp/servers/{name}` | GET | Get server detail + tool list |
| `/v1/mcp/servers/{name}` | DELETE | Disconnect server |
| `/v1/mcp/servers/{name}/tools` | GET | List tools provided by server |
| `/v1/mcp/servers/{name}/scan` | POST | Security scan server tools |
| `/v1/mcp/discover` | POST | Auto-discover tools from URL |

Features:
- Three tabs: Connected | Registry | Add
- Server cards: name, status (connected/disconnected/error), tool count, uptime
- Add flow: enter MCP server URL → auto-discover tools → security scan → connect
- Tool list with JSON schema display per tool
- Import flow same as Skills (scan → findings → connect)

---

### Page: CLI Terminal (`/cli`)

Embedded terminal for CLI-Anything integration — headless Inkscape/Gimp canvas manipulation in the browser.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/cli/session` | POST | Create terminal session |
| `/v1/cli/session/{id}/exec` | POST | Execute command |
| `/v1/cli/session/{id}` | GET (WS) | WebSocket for output stream |

Features:
- xterm.js embedded terminal with full ANSI color support
- Command history (up/down arrows)
- Tab completion for CLI-Anything commands
- Split pane option (terminal left + canvas preview right)
- CLI-Anything integration: canvas create, layer add, shape draw, export — all via CLI

---

### Page: Container Builder (`/containers`)

Visual Docker container builder for custom MCP servers and agent environments.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/containers/build` | POST | Build image from Dockerfile |
| `/v1/containers/images` | GET | List built images |
| `/v1/containers/images/{id}` | DELETE | Remove image |
| `/v1/containers/push` | POST | Push image to registry |
| `/v1/containers/suggest` | POST | AI-generate Dockerfile from description |

Features:
- Three-step wizard: Base Image → Configure → Build
- Base image selector: Python 3.12, Node 20, Ubuntu 24.04, etc.
- Dockerfile editor with syntax highlighting
- AI suggest: describe what the container should do → generates Dockerfile
- Build progress with live log output
- Push to registry option (GHCR, Docker Hub, custom)

---

### Page: Memory Explorer (`/memory`)

Browse and manage 8-tier episodic memory.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/memory` | GET | List memories (paginated, filterable by tier) |
| `/v1/memory/{id}` | GET | Get memory detail |
| `/v1/memory/{id}/reinforce` | POST | Reinforce memory (+weight) |
| `/v1/memory/{id}/decay` | POST | Decay memory (-weight) |
| `/v1/memory/{id}` | DELETE | Soft-delete memory |
| `/v1/memory/{id}/contradict` | POST | Register contradiction |
| `/v1/memory/stats` | GET | Memory statistics by tier |
| `/v1/learnings` | GET | List learnings |
| `/v1/learnings/{id}` | PUT | Update learning |
| `/v1/learnings/{id}/promote` | POST | Promote learning |
| `/v1/learnings/{id}/demote` | POST | Demote learning |

Features:
- Tier filter sidebar with count badges: OBSERVATION(34) HYPOTHESIS(12) OPINION(8) LESSON(5) REGRET(3) ACCOMPLISHMENT(7) AFFIRMATION(2) WISDOM(1)
- Memory cards: content preview, tier badge, weight gauge (visual bar), source badge (I_DID/I_WAS_TOLD/I_IMAGINED), reinforcement count, timestamp
- Actions per card: reinforce, decay, soft-delete, contradict
- Full-text search across all memories
- Stats header: total count, average weight, reinforcement rate, WISDOM count
- Weight bounds enforced per tier (OBSERVATION 0.1-0.5, WISDOM 0.9-1.0)
- Durable tiers (REGRET, ACCOMPLISHMENT, AFFIRMATION, WISDOM) cannot be soft-deleted

---

### Page: Settings (`/settings`)

System configuration, auth, feature flags.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/admin/config` | GET | Get current config |
| `/v1/admin/config` | PUT | Update config |
| `/v1/admin/reload` | POST | Hot-reload config.yaml |
| `/health` | GET | Health check |
| `/health/ready` | GET | Readiness (DB + LiteLLM + circuit breaker) |
| `/v1/admin/audit` | GET | Audit log entries |
| `/v1/status/quotas` | GET | Provider quota usage |
| `/v1/status/outcomes` | GET | Task outcome statistics |

Features:
- Five tabs: General | Models | Auth | Tools | Features
- General: app name, default model, debug mode, auth toggle, LiteLLM URL + key, database URL, Langfuse keys
- Models: table of configured models with provider, tier, quality weight, cost weight, active toggle, test button
- Auth: API key management, JWT config, service key CRUD
- Tools: MCP server connection status and management
- Features: toggle switches for all feature flags:
  - `turing_enabled` — Enable autonoetic self-model
  - `heartbeat_enabled` — Autonomous initiative engine
  - `dream_loop_enabled` — Idle-time memory consolidation
  - `red_team_enabled` — Weekly self-hardening security
  - `skill_forge_enabled` — Self-authoring skills
  - `stress_rehearsal_enabled` — Controlled chaos testing
  - `ultra_think_enabled` — Parallel diverse generation
  - `message_board_enabled` — Proactive agent→human communication
  - `evolution_tracking` — Git-tracked memory mutations

---

## Application Shell

### Layout

Sidebar + main content pattern on all pages:

```
┌──────────────────────────────────────────────────┐
│ Topbar: Logo | Page Title | Notifications | User │
├────────┬─────────────────────────────────────────┤
│ Side   │  Main Content Area                      │
│ nav    │  (varies per page)                       │
│        │                                         │
│ 48px   │  flex: 1                                │
│ icons  │                                         │
│ or     │                                         │
│ 240px  │                                         │
│ expand │                                         │
├────────┼─────────────────────────────────────────┤
│        │ Status bar (connection, model, health)   │
└────────┴─────────────────────────────────────────┘
```

Sidebar items (top to bottom):
1. Chat (`/`)
2. Missions (`/missions`)
3. Schedules (`/schedules`)
4. Skills (`/skills`)
5. Agents (`/agents`)
6. MCP (`/mcp`)
7. CLI (`/cli`)
8. Containers (`/containers`)
9. Memory (`/memory`)
10. Settings (`/settings`)

### Responsive Breakpoints

| Breakpoint | Layout |
|---|---|
| Desktop (>=1024px) | Sidebar expanded (240px) + main content |
| Tablet (768-1023px) | Sidebar collapsed (48px icons) + main content |
| Mobile (<768px) | No sidebar, bottom tab bar, hamburger for full nav |

### Status Bar (bottom, 28px fixed)

- Left: connection status dot + "Connected" / "Reconnecting..."
- Center: active model name + tier badge
- Right: token usage meter, session timer

### Shared Components

| Component | Used On | Notes |
|---|---|---|
| StatusBadge | Everywhere | Color-coded: running=phosphor, complete=phosphor solid, blocked=burn, warning=amber, idle=grey |
| TrustTierBadge | Skills, Agents | Skull/T3/T2/T1/T0 with distinct styling |
| AgentBadge | Chat, Missions | Agent name + icon |
| ModelBadge | Chat | Model name + provider |
| IntentBadge | Chat | Task type label |
| SecurityScanPanel | Skills, Agents, MCP | Expandable findings list with severity chips |
| CronInput | Schedules | Text input + visual next-run helper |
| CodeEditor | Skills, Agents, Containers | Syntax-highlighted YAML/Dockerfile editor |
| MarkdownRenderer | Chat, Missions | Markdown + code highlighting + LaTeX |
| Timeline | Missions | Vertical event timeline with timestamps |
| ChatBubble | Chat, Missions | User + assistant message bubbles |
| Card | Everything | Panel container with header/body/footer |
| Modal | Everything | Dialog overlay |
| EmptyState | Everything | Icon + message + optional CTA button |
| Toggle | Settings, Features | On/off switch |
| Toast | Everywhere | Success/error/warning notifications |

---

## Design System Foundation

### Existing Theme: Phosphor Noir

Production-tested dark theme. Use as foundation.

| Token | Hex | Usage |
|---|---|---|
| `--ink-0` | `#050507` | Deepest background |
| `--ink-1` | `#0A0B0A` | Page background |
| `--ink-2` | `#0F1110` | Recessed panels |
| `--ink-3` | `#141714` | Elevated surfaces |
| `--ink-4` | `#1B1F1C` | Cards/panels |
| `--ink-5` | `#222825` | Input backgrounds |
| `--line-1` | `#232925` | Subtle borders |
| `--line-2` | `#334038` | Strong borders |
| `--phosphor-hi` | `#A8FF8E` | Hover states, highlights |
| `--phosphor` | `#5EE88C` | Primary accent |
| `--phosphor-dim` | `#1E7A3D` | Subtle accent backgrounds |
| `--amber` | `#FFB547` | Warnings |
| `--burn` | `#FF5A4E` | Destructive, errors |
| `--bone-0` | `#F2F0EA` | Headings |
| `--bone-1` | `#ECEAE3` | Primary text |

Typography:
- Display: `VT323` (pixel font) for headings
- Body: `IBM Plex Sans` for content
- Mono: `IBM Plex Mono` for code, labels, tags
- Serif: `IBM Plex Serif` for long-form content

Spacing: 4px grid (4/8/12/16/24/32/48/64/96px)

Motion:
- Hover: 120ms
- State change: 220ms
- Scene transition: 600ms

Note: Hive Conductor should have its own accent color identity, distinct from Stronghold's castle theme and the existing Phosphor Noir dashboard. The token structure and dark theme stay, but the accent color family may shift.
