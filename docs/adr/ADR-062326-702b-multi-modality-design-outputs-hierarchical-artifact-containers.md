---
id: ADR-062326-702b
title: Multi-modality design outputs and hierarchical artifact containers
repo: maistro-engine
kind: adr
status: Proposed
created: 2026-06-23
substrate:
  - maistro-engine#ADR-061
  - maistro-engine#ADR-100
  - maistro-engine#ADR-062
implements: []
related: []
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Ability
owners:
  - '@BlakeMatthews-dev'
---

# ADR-062326-702b: Multi-modality design outputs and hierarchical artifact containers

## Context

ADR-061 specifies that `DesignEngine` builds a prompt stack but does not emit the actual artifact
(that is the caller's responsibility after LLM invocation). Today `DesignOutput.content` is a single
`str` field, which works for text formats (HTML, CSS, Markdown, JSON) but fails for:

1. **Multi-file outputs** — HTML+CSS+JS require separate files, not a single string.
2. **Binary formats** — PNG, PDF, SVG as bytes (not base64'd strings).
3. **Nested/scoped artifacts** — a single output should be able to hold multiple assets
   (e.g., `rasters.characters.{name}`, `svg.typography.{section}`, `html.pages.{slug}`),
   not a flat collection.

Current workarounds (storing URLs in the `url` field, relying on CanvasRecord for rasters)
do not compose with the trust-tier model (ADR-061 §3) or survive session/project lifecycle
boundaries.

## Decision

### 1. Hierarchical artifact container replaces single-string `DesignOutput.content`

```python
@dataclass
class ArtifactNode:
    """A single artifact (file, binary blob, or nested container)."""
    key: str  # kebab-case identifier within parent, e.g. "main", "sidebar", "characters"
    kind: Literal["file", "blob", "container"]  # file/text, binary data, or nested
    format: OutputFormat  # HTML, CSS, PNG, SVG, etc.
    value: str | bytes | None = None  # content for file/blob; None for container
    children: dict[str, ArtifactNode] = field(default_factory=dict)  # nested artifacts
    metadata: dict[str, Any] = field(default_factory=dict)  # e.g. "width": 1920

@dataclass
class DesignOutput:
    """A generated design artifact (multi-modality, hierarchical)."""
    root: ArtifactNode  # root container holding the artifact tree
    trust_tier: TrustTier = TrustTier.T3
    metadata: dict[str, Any] = field(default_factory=dict)  # output-level metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

Examples:

- **Single-file HTML output** → `root.kind="file"`, `root.format=HTML`, `root.value="<html>..."`
- **Landing page (HTML+CSS+JS)** → `root.kind="container"`, `root.children={"index.html": File(HTML), "style.css": File(CSS), "app.js": File(JS)}`
- **Hero image** → `root.kind="blob"`, `root.format=PNG`, `root.value=<bytes>`
- **SVG with nested typography** → `root.kind="container"`, `root.format=SVG`, `root.children={"header": Container(typography.subfields...), "body": ...}`
- **Pitch deck with asset pack** → `root.kind="container"`, `root.children={"slides.html": File(HTML), "assets.rasters": Container({"slide-1-hero.png": Blob, ...}), "fonts": Container({...})}`

### 2. Output scanning (Warden) gates multi-modality artifacts

All output content (HTML, SVG, JS, CSS strings) is scanned before return, since outputs carry
the session's contaminated trust tier. Scanning detects script injection, eval, iframes,
prompt-injection phrasing, external URL fetches (against an allowlist), and steganographic content.
Raises `TrustBannedError` if banished patterns are found. This mirrors the design-system-import
scan (ADR-100 § 2) applied at output time rather than input time.

### 3. Binary-safe asset store (canvas or new)

Blob artifacts must be persisted. Canvas asset store (ADR-040) is the natural home for
`DesignOutput` blobs; the DesignEngine integrates with `CanvasStore` protocol but does not
require it (callers can substitute an in-memory store or cloud blob store).

### 4. Add `JS` to `OutputFormat`

```python
class OutputFormat(StrEnum):
    HTML = "html"
    MARKDOWN = "markdown"
    PPTX = "pptx"
    PNG = "png"
    SVG = "svg"
    PDF = "pdf"
    CSS = "css"
    JSON = "json"
    JS = "js"      # ← NEW
```

### 5. Renderer protocols per modality

Define abstract interfaces for each renderer backend (caller injects):

```python
@runtime_checkable
class HTMLRenderer(Protocol):
    async def render(self, html: str, css: str | None = None) -> bytes: ...  # → PNG/PDF

@runtime_checkable
class SVGRenderer(Protocol):
    async def render(self, svg: str, format: Literal["png", "pdf"]) -> bytes: ...

@runtime_checkable
class TypographyRenderer(Protocol):
    async def render_text(self, text: str, font: TypographyToken, size: str) -> bytes: ...
```

The engine accepts these optionally; skills declare which renderers they require. If a skill
needs an unavailable renderer, raise `SkillModeError` (mirroring the image_gen check today).

### 6. DesignOrchestrateNode integrates hierarchical outputs

The DAG node now produces `DesignOutput` with hierarchical containers, not flat strings.
Downstream nodes (or the DAG executor) can traverse the tree and fan out to per-artifact
processing (store, serve, convert formats, etc.).

## Acceptance criteria

```gherkin
Scenario: Single-file HTML output nests under root container
  Given a skill with mode=PROTOTYPE, output_formats=[HTML]
  When generate() is called
  Then output.root.kind == "container"
  And output.root.children["index"] is ArtifactNode with kind="file", format=HTML

Scenario: Multi-file landing page (HTML+CSS+JS)
  Given a skill with output_formats=[HTML, CSS, JS]
  When generate() is called
  Then output.root.children contains "index.html", "style.css", "app.js"

Scenario: PNG output is a blob
  Given a skill with mode=IMAGE
  When generate() is called
  Then output.root.kind == "blob", format=PNG, value is bytes

Scenario: SVG with nested typography hierarchy
  Given SVG output with typography subfields
  Then output.root.children["typography"] is Container
  And output.root.children["typography"].children["header"] is File(SVG)

Scenario: Warden scan detects <script> injection in HTML output
  Given output containing "<script>alert(1)</script>"
  When output is scanned before return
  Then TrustBannedError is raised

Scenario: SkillModeError if HTML renderer unavailable
  Given a skill requiring HTMLRenderer (mode=TEMPLATE)
  When DesignEngine is constructed without an HTMLRenderer
  Then generate() raises SkillModeError

Scenario: Blob artifact is persisted via CanvasStore
  Given output.root.kind == "blob", format=PNG
  When DesignProject is persisted
  Then blob is stored in canvas asset store (or injected store)
```

## Consequences

**Positive:**
- Multi-file outputs (HTML+CSS+JS) compose naturally without flattening or post-processing.
- Binary-safe; PNG/PDF/SVG bytes do not require base64 encoding.
- Hierarchical nesting mirrors skill intent (e.g., "hero section" → `root.children.hero`).
- Warden scanning per output (not per skill) catches runtime injection from LLM outputs.
- Trust tier is carried through the tree; all artifacts are downgraded together.

**Negative:**
- More complex than a single-string output; callers traverse the tree instead of reading `.content`.
- HTML renderer (→ PNG/PDF rasterization) requires a headless browser or wkhtmltopdf-class backend.
- Rendering backends are optional; skills without their renderer raise errors (non-composable until a caller provides one).

**Neutral:**
- Backward compatibility: existing text-only skills produce `root.kind="file"` (can be read as `.root.value`).

## Out of scope

- Rendering pipeline orchestration (how to chain rasterizers); that is a caller concern.
- Mutation of outputs post-generation (editing individual artifacts). Outputs are immutable once created.
- Streaming or chunked artifact generation (ADR-062 graph streaming may interact).
- Typography rendering without an injected renderer (not a blocker, just an optional feature).
