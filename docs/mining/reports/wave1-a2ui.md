# Wave-1 report: A2UI (condensed digest)

**Verdict: genuinely novel to the engine; adoption already committed but never formalized.**

A2UI (`/home/user/A2UI`, Apache 2.0, fork of Google's A2UI, v0.8→v0.10 specs) is an open
protocol + libraries letting agents "speak UI": declarative JSON describing UI *intent*
(component tree + data model); client renderers map to native widgets (React/Lit/Angular/
Flutter). Philosophy: **"safe like data, expressive like code"** — agents may only request
components from a client-side **catalog** of pre-approved components.

Key concepts: **surfaces** (addressable UI regions, `surfaceId`; messages createSurface/
updateComponents/updateDataModel/deleteSurface/callFunction/actionResponse —
`specification/v0_10/json/server_to_client.json`); **adjacency-list component model** (flat
id-referenced list, LLM-streamable, incrementally patchable); **data binding** via JSON-Pointer
(RFC 6901), templates for lists, bidirectional inputs; **actions** (client→server `event` vs
local `functionCall`, renderer-side `checks`); **catalog negotiation** via capabilities (~17
basic components); **transport** over A2A (extension URI
`https://a2ui.org/a2a-extension/a2ui/v0.10`) or AG-UI/SSE/WebSocket; **Python agent SDK**
(`agent_sdks/python/src/a2ui/` — A2uiSchemaManager generates LLM system prompts from catalogs,
A2uiValidator, streaming JSON parse-and-heal `payload_fixer.py`, A2A extension helpers).

**Engine status (verified):** BACKLOG already commits — `[engine-090]` chat-UI integration
contract (OpenAI-compat + A2UI + MCP), `[engine-091]` A2UI version-pin, `[sh-602]` A2UI render
layer; INSPIRATIONS.md:82 lists it as substrate; SPEC-179 FR-5 assumes A2UI URLs in the Flutter
gateway WebView. But **no ADR, no spec, no code**. maistro-design emits *generated code*
(REACT_TSX/HTML/SVG — the opposite trust posture); its "renderers" are rasterizers (→bytes);
`ArtifactNode` (ADR-062326-702b) is a static output tree, not a live surface; `DesignSystem
.components` is a bare `list[str]` with no enforceable catalog schema; canvas is image layers.
`TrustTier` + Warden philosophy maps exactly onto A2UI's catalog boundary but is unused for UI.

**Ranked actions:**
1. ADR: adopt/interoperate with A2UI; close [engine-090]/[engine-091]; pin version (v0.10). (L)
2. SPEC: A2UI surface flow through the engine — conduit emits A2UI messages; catalog approval =
   TrustTier; inbound `action` events re-enter conduit as requests. (M)
3. Integrate the Apache-2.0 Python SDK behind an engine protocol (DI rule: no direct import in
   business logic); highest-reuse: schema-manager prompt generation + streaming healer. (M)
4. Component catalog schema unified with `DesignSystem` tokens + per-catalog TrustTier, wired to
   the existing trust review queue. (M)
5. Reserve the A2A UI-extension slot in ADR-058 so delegated sub-agents can return surfaces. (S)
6. Renderers: reference only — `renderers/react` for canvas frontend, `renderers/flutter` for
   SPEC-179. No engine-side port. Conformance suite → mirror into formal/ later.
