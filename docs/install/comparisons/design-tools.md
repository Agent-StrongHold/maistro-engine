# AI design tools — open-source options vs. our own stack

A side-by-side of three open-source "prompt → design artifact" tools against the
three design capabilities we ship in this monorepo. The point is not to pick a
"winner": the open-source tools are **end-to-end products**, ours are
**composable libraries/protocols** that a product (Agent Conductor, Stronghold,
the book-maker POC) wires up. They occupy different layers.

> Context: we already vendor `nexu-io/open-design`'s Apache-2.0 design-system
> corpus into `maistro-design` — see [ADR-100](../../adr/ADR-100-bundled-open-design-systems.md)
> and [SPEC-234](../../specs/SPEC-234-bundled-open-design-systems.md). So this is
> as much "what else can we borrow" as "how do we compare."

---

## The open-source options

### 1. Open Design — `nexu-io/open-design`

- **What:** "Vibe Design Workspace," an open-source alternative to Anthropic's
  (closed, cloud-only) Claude Design. Your coding agent *becomes* the design
  engine.
- **License:** Apache-2.0 (bundled `guizang-ppt`/`html-ppt`/`web-clone` keep MIT).
- **Architecture:** Electron desktop shell + Next.js 16 / React 18 frontend +
  a local Node 24 / Express / SQLite daemon on `127.0.0.1`. Installs as an **MCP
  stdio server into 22+ CLIs** (Claude Code, Codex, Cursor, Copilot, Gemini,
  Qwen, …). The agent reads `SKILL.md` + `DESIGN.md` and writes real artifact
  files to disk; a sandboxed iframe previews them. Also ships a BYOK proxy
  (`/api/proxy/{anthropic,openai,azure,google,ollama}`) with SSRF protection.
- **Produces:** web/mobile/desktop prototypes, landing pages, dashboards, decks,
  emails, images, **video** (HyperFrames: HTML+CSS+GSAP → deterministic MP4 via
  headless Chrome + FFmpeg, HeyGen's OSS framework).
- **Content library:** ~100–259 skills, **150 design systems** (Linear, Stripe,
  Vercel, Apple, Notion, …), 261 plugins. Design systems are a 9-section
  Markdown schema (`DESIGN.md`) — plain prose + tokens, no code.
- **Export:** HTML (single-file), PDF, PPTX, MP4, ZIP, Markdown.
- **Maturity:** very active, broad scope. This is the richest of the three.

### 2. Open CoDesign — `OpenCoworkAI/open-codesign`

- **What:** Desktop AI design tool; another local-first Claude Design
  alternative. Prompt → prototype / slides / marketing assets.
- **License:** MIT.
- **Architecture:** Electron desktop app (macOS/Windows/Linux) — React 19,
  Vite 6, Tailwind v4, TypeScript. BYOK: Anthropic, OpenAI, Gemini, DeepSeek,
  OpenRouter, SiliconFlow, local Ollama, ChatGPT-subscription login, or any
  OpenAI-compatible endpoint; one-click import of Claude Code / Codex configs.
- **Produces:** 12 built-in skill modules — slide decks, dashboards, landing
  pages, SVG charts, glassmorphism, editorial typography, heroes, pricing,
  footers, chat UIs, data tables, calendars.
- **Standout UX:** click any element in the preview, **drop a pin, leave a note,
  and the model rewrites only that region** — targeted edits without full
  regeneration. Sessions persist as JSONL history + on-disk workspace folders.
- **Export:** HTML, PDF, PPTX, ZIP, Markdown.
- **Maturity:** v0.2.0 (May 2026), ~7k stars. Tighter/simpler scope than Open
  Design.

### 3. Presenton — `presenton/presenton`

- **What:** Open-source AI **presentation** generator + API (Gamma / Beautiful
  AI / Decktopus alternative). Narrowest scope, deepest at that one thing.
- **License:** Apache-2.0.
- **Architecture:** FastAPI backend + Next.js frontend; Docker (GPU-capable) or
  Electron desktop. **REST API for programmatic/embedded generation.** Mem0
  (local Qdrant + SQLite) for presentation-scoped memory.
- **Produces:** slide decks from a prompt, uploaded documents, or markdown —
  configurable slide count, tone, verbosity, language; TOC + title slides.
- **Models/images:** OpenAI, Gemini, Vertex, Azure, Anthropic, Bedrock,
  Fireworks, Together, Ollama, LM Studio + OpenAI-compatible; images via DALL-E
  3, Gemini Flash, Pexels, Pixabay, ComfyUI.
- **Export:** **PPTX (fully editable)** + PDF. Custom templates via HTML+Tailwind
  or generated from an existing `.pptx`.
- **Maturity:** ~9k stars, 64 releases. The most "productionized" of the three,
  but presentations only.

---

## Our own stack

### 4. maistro-canvas — layer-based image compositor

- **What:** A pixel-level, layer-based image compositing *ability* (PIL/RGBA,
  back-to-front assembly), not a design-intent tool. Async PostgreSQL
  persistence, FastAPI routes, agent-facing `canvas` / `canvas_asset` tools
  (generate / refine / reference / composite / text). ~6.2k lines of engine.
- **Scene graph:** ADR-039 asset model — `LayerKind`, sockets/slots, anchors,
  occlusion DAG, transforms, character poses, personalization slots
  (child-profile driven).
- **Consumer app:** a React book-maker POC — phased children's-book pipeline
  (Story → Style → Character → Storyboard → Pages) with **real Lulu
  print-on-demand** ordering and PDF export.
- **Delegation:** the image backend is a `Protocol` (`ImageGenClient`); no
  concrete client ships. Production expects a local P40 image-gen server.
- **Maturity:** library **implemented**; book-maker frontend is a **POC**.

### 5. da Vinci agent — visual-artist persona

- **What:** A declarative agent (YAML + `SOUL.md` + `RULES.md`) that *drives* the
  canvas tools — a creative-director persona, not code.
- **Workflow:** Listen → Plan Layers → Draft Fast (cheap models) → Rough
  Composite → Proof Render (approval-gated) → Refine. Ships a **priced
  model-selection playbook** (draft tier free→$0.002, proof tier up to $0.03,
  <$0.50/scene budget) and craft rules (lighting consistency, no baked-in text,
  character isolation).
- **Maturity:** a complete spec/persona; execution depends on the agent runtime.

### 6. maistro-design — design skills + systems + trust orchestration

- **What:** The closest analog to the open-source tools — composable
  `DesignSkill`s (pitch-deck, landing-page, login-flow, email-template, brand
  guidelines, …) × `DesignSystem`s, with a `DesignOrchestrateNode` that plugs
  into the maistro-core DAG. Governed by
  [ADR-061](../../adr/ADR-061-maistro-design-package.md) / ADR-100 / SPEC-234.
- **Critical difference:** **"DesignEngine builds artifacts; it does not call an
  LLM."** It assembles a *trust-scanned prompt stack* (skill instructions +
  design-system `DESIGN.md`/tokens + discovery answers) and hands off to the
  caller's LLM + renderer protocols. It does **not** render finished decks/pages
  itself.
- **Trust model:** monotonic contamination (t0 > t1 > t2 > t3 > skull),
  Warden + banish-list scanning of both inputs and outputs, per-execution
  session-scoped isolation — a governance layer the OSS tools don't have.
- **Content:** 10 built-in T0 skills + the 150-system open-design corpus (6
  bundled T1, 144 catalog T2).
- **Maturity:** **implemented** as a foundation layer — not a self-contained
  generator.

---

## Feature matrix

| | Open Design | Open CoDesign | Presenton | maistro-canvas | da Vinci | maistro-design |
|---|---|---|---|---|---|---|
| **Category** | Full design workspace | Desktop design tool | Presentation gen | Image compositor | Agent persona | Design skills/systems lib |
| **License** | Apache-2.0 | MIT | Apache-2.0 | Apache-2.0 | Apache-2.0 | Apache-2.0 |
| **Form factor** | Electron + daemon + MCP | Electron | Docker/API + Electron | Python lib + FastAPI | YAML/prompt spec | Python lib + DAG node |
| **End-to-end?** | ✅ prompt→artifact | ✅ | ✅ | ⚠️ needs image backend | ⚠️ needs runtime | ❌ prompt-stack only |
| **Calls the LLM itself** | ✅ (or via CLI agent) | ✅ | ✅ | n/a (image only) | via runtime | ❌ by design |
| **Prototypes / landing pages** | ✅ | ✅ | ❌ | ❌ | 🎯 skill (delegated) | — |
| **Slide decks** | ✅ | ✅ | ✅✅ (focus) | ❌ | 🎯 skill (delegated) | — |
| **Images** | ✅ | limited | ✅ (stock/gen) | ✅✅ (compositing) | ✅✅ | 🎯 skill |
| **Video** | ✅ (HyperFrames) | ❌ | ❌ | ❌ | ❌ | mode exists |
| **Export** | HTML/PDF/PPTX/MP4/ZIP/MD | HTML/PDF/PPTX/ZIP/MD | PPTX/PDF | PDF (book) | — | delegated |
| **Design systems** | 150 | (styling built-in) | templates | ❌ | ❌ | 150 (from Open Design) |
| **BYOK multi-model** | ✅ 22+ CLIs | ✅ | ✅ many | protocol | model playbook | delegated |
| **Multi-tenancy / trust tiers** | ❌ | ❌ | ❌ | org-scoped | trust t1 | ✅✅ trust contamination |
| **Print-on-demand** | ❌ | ❌ | ❌ | ✅ Lulu | ❌ | ❌ |

---

## How to read this

**Different layers, not competitors.**

- **Open Design / Open CoDesign / Presenton** are *finished products*: install,
  give a prompt, get a deck/page/video. Their design engine is "an LLM (or a
  coding-agent CLI) writes real HTML/CSS/PPTX files and previews them in a
  sandbox." Presenton is the one to embed if you only need **decks via an API**.
- **maistro-design** is the *governance + composition layer* that a product like
  Stronghold needs and the OSS tools lack: trust-tiered scanning, scope axes,
  skill/system registries, DAG orchestration. It deliberately stops at
  prompt-stack assembly and delegates rendering.
- **maistro-canvas** is a genuinely *different capability* none of the three
  have: deterministic, layer-based **pixel compositing** with a scene graph,
  personalization, and a real POD pipeline. Open Design's HyperFrames is the
  nearest neighbor (HTML→MP4), but that's animation, not layered raster
  compositing.
- **da Vinci** is the persona that turns canvas into a directed workflow.

**What we can borrow (some already borrowed).**

1. ✅ **Design-system corpus** — already vendored from Open Design (ADR-100).
   Worth a re-sync pipeline (SPEC-234 lists this as a non-goal today).
2. **Coding-agent-as-design-engine (MCP) pattern** — Open Design's model of
   installing as an MCP server into any CLI and writing real files is a clean way
   to give `maistro-design` an actual renderer without building our own. It maps
   onto our "DesignEngine delegates rendering" boundary.
3. **Region-pin refinement** (Open CoDesign) — "pin a spot, rewrite just that
   region" is directly analogous to da Vinci's img2img region refinement; worth
   mirroring in the book-maker UI.
4. **Presenton as the deck renderer** — rather than build our own PPTX exporter,
   `maistro-design`'s `pitch-deck` / `product-demo-deck` skills could target
   Presenton's REST API as a `required_renderer` backend.
5. **HyperFrames (HTML→MP4)** — fills the one format we have no story for
   (`SkillMode.video` exists but nothing renders it).

**Where we're genuinely differentiated:** trust-tier governance + scope/tenancy
(none of the three have it), deterministic layered image compositing + scene
graph, and the Lulu print-on-demand path. Those are the pieces to keep building
in-house; decks, generic prototypes, and video are candidates to *integrate*
rather than reimplement.

---

## Sources

- Open Design — <https://github.com/nexu-io/open-design>
- Open CoDesign — <https://github.com/opencoworkai/open-codesign>
- Presenton — <https://github.com/presenton/presenton>, <https://presenton.ai/>
- Our stack — `packages/maistro-canvas/`, `packages/maistro-canvas/agents/davinci/`,
  `packages/maistro-design/`; ADR-061, ADR-100, SPEC-234.
