---
id: SPEC-062326-7dcb
title: "ArtifactNode hierarchy and output-side Warden scanning for maistro-design"
repo: maistro-engine
kind: spec
status: Implemented
created: 2026-06-23
substrate:
  - maistro-engine#ADR-061
  - maistro-engine#ADR-100
  - maistro-engine#ADR-062
implements:
  - maistro-engine#ADR-062326-702b
related: []
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests:
  - packages/maistro-design/tests/test_design.py
  - packages/maistro-design/tests/test_scan.py
layer: Ability
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-062326-7dcb: ArtifactNode hierarchy and output-side Warden scanning

## Context

ADR-062326-702b replaced `DesignOutput`'s flat `content: str` with a hierarchical
`ArtifactNode` tree (`file` / `blob` / `container`) so a single output can carry
multiple named, addressable artifacts — e.g. `rasters.characters.joe-smith`,
`svg.typography.header` — instead of one opaque string. It also added an
output-side Warden scan (mirroring the existing design-system-import scan) so
generated content is checked for injected scripts/prompt-injection/banished
patterns before it leaves `DesignEngine.generate()`, and renderer protocols
(`HTMLRenderer`, `SVGRenderer`, `TypographyRenderer`) that skills can require.
This SPEC documents the shipped implementation.

## Goals

- Document the actual `ArtifactNode`/`ArtifactKind`/`DesignOutput` shape as coded.
- Document `scan_design_output()` and how it tags findings with dotted artifact
  addresses.
- Document the renderer-availability gate (`_check_renderer_available`) and how
  it mirrors the existing `_check_image_gen` pattern.
- Map ADR-062326-702b's Gherkin acceptance scenarios to real tests.

## Non-goals

- Rendering pipeline orchestration (chaining rasterizers) — caller concern.
- Mutation of outputs post-generation — outputs are immutable once created.
- Streaming/chunked artifact generation.
- Typography rendering without an injected `TypographyRenderer` — optional, not
  a blocker.

## Decision

`packages/maistro-design/src/maistro_design/types.py`:

```python
class ArtifactKind(StrEnum):
    FILE = "file"
    BLOB = "blob"
    CONTAINER = "container"

@dataclass
class ArtifactNode:
    key: str
    kind: ArtifactKind
    format: OutputFormat | None = None
    value: str | bytes | None = None
    children: dict[str, ArtifactNode] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, address: str) -> ArtifactNode | None: ...   # dotted-path lookup
    def walk(self, _prefix: str = "") -> Iterator[tuple[str, ArtifactNode]]: ...  # FILE/BLOB leaves

@dataclass
class DesignOutput:
    root: ArtifactNode
    url: str | None = None
    trust_tier: TrustTier = TrustTier.T3
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def format(self) -> OutputFormat | None: ...   # root.format
    @property
    def content(self) -> str: ...    # root.value; raises DesignOutputShapeError unless
                                       # root.kind is FILE and root.value is str
```

`RendererKind = Literal["html", "svg", "typography"]`; `DesignSkill` gained
`required_renderer: RendererKind | None = None`. `OutputFormat` gained `JS`.

`packages/maistro-design/src/maistro_design/scan.py` (new module):

```python
def scan_design_output(
    output: DesignOutput, *,
    banish_list: InMemoryTrustBanishList | None = None,
    url_allowlist: tuple[str, ...] = DEFAULT_URL_ALLOWLIST,
) -> ScanReport: ...
```

Walks `output.root.walk()`, scanning each `FILE` leaf's string `value` through
the same `scan_blocking_patterns`/`find_external_urls` primitives used for
design-system-import scanning (`scan_design_system_content`, now also sourced
from this module rather than duplicated in `systems/importer.py`). `BLOB` leaves
are skipped (binary content is not pattern-scanned). Blocking flags are tagged
with the leaf's dotted address, e.g. `"svg.typography.header: matched script
pattern ..."`.

`packages/maistro-design/src/maistro_design/engine.py`:

```python
def _build_output(prompt_stack: str, trust_tier: TrustTier) -> DesignOutput: ...
    # wraps the assembled prompt stack as a single FILE-kind ArtifactNode

def _scan_output_or_raise(output: DesignOutput, banish_list: InMemoryTrustBanishList) -> None: ...
    # raises TrustBannedError if scan_design_output(...).passed is False

class DesignEngine:
    def __init__(
        self, skill_registry, system_registry,
        banish_list=None, trust_review_queue=None,
        canvas_store=None, image_gen=None,
        html_renderer: HTMLRenderer | None = None,
        svg_renderer: SVGRenderer | None = None,
        typography_renderer: TypographyRenderer | None = None,
    ) -> None: ...

    def _check_renderer_available(self, skill: Any) -> None: ...
        # raises SkillModeError if skill.required_renderer is set and the
        # matching renderer attribute (via _RENDERER_ATTRS) is None
```

`generate()`'s pipeline now runs `_check_image_gen` and
`_check_renderer_available` alongside `_check_compatibility` before
contamination, and scans the assembled prompt stack via `_scan_output_or_raise`
after `_build_prompt_stack` — independent of, and in addition to,
`_scan_discovery_responses` (which only sees `discovery.responses`, not a
skill's `system_prompt` or a design system's `design_md`/`tokens_css`).

`packages/maistro-design/src/maistro_design/protocols.py` gained
`HTMLRenderer`, `SVGRenderer`, `TypographyRenderer` (`@runtime_checkable`
`Protocol`), each with one `async` render method (`render`/`render_text`)
returning `bytes`.

Today the engine only ever constructs a single `FILE`-kind root (one prompt
stack, format `MARKDOWN`); the renderer protocols and multi-artifact container
shape exist on the type/contract level for callers and future skills to use,
but `DesignEngine.generate()` does not yet itself produce multi-file or blob
outputs. `DesignOrchestrateNode` (`nodes.py`) is unaffected: it reads
`project.outputs[0].content`, which continues to resolve through the new
`DesignOutput.content` property unchanged.

## Acceptance criteria

- [x] Single-file HTML/text output nests under `root.kind == ArtifactKind.FILE`
- [x] `ArtifactNode.walk()` yields dotted addresses for every `FILE`/`BLOB` leaf,
      recursing through `CONTAINER` nodes
- [x] `ArtifactNode.get(address)` resolves a dotted path through `.children`
- [x] `DesignOutput.content`/`.format` raise `DesignOutputShapeError` for
      non-single-file (`container`/`blob`) roots
- [x] `OutputFormat.JS` exists
- [x] Warden scan detects `<script>` injection in generated output, tagged with
      the leaf's dotted address
- [x] `SkillModeError` raised if a skill's `required_renderer` has no matching
      renderer injected into `DesignEngine`
- [x] `generate()` succeeds when the required renderer is provided

## Testing

`packages/maistro-design/tests/test_design.py`:
- `TestArtifactNode::test_get_resolves_dotted_address_through_containers`
- `TestArtifactNode::test_get_returns_none_for_unknown_address`
- `TestArtifactNode::test_walk_yields_dotted_addresses_for_every_leaf`
- `TestArtifactNode::test_walk_on_single_file_root_yields_its_own_key`
- `TestDesignOutput::test_content_and_format_for_single_file_output`
- `TestDesignOutput::test_content_raises_shape_error_for_container_root`
- `TestDesignOutput::test_content_raises_shape_error_for_blob_root`
- `TestDesignOutput::test_output_format_includes_js`
- `TestDesignEngineGenerate::test_generate_scans_assembled_output_for_script_injection`
- `TestDesignEngineGenerate::test_generate_output_is_a_file_artifact`
- `TestDesignEngineGenerate::test_generate_raises_skill_mode_error_for_missing_renderer`
- `TestDesignEngineGenerate::test_generate_succeeds_when_required_renderer_is_provided`

`packages/maistro-design/tests/test_scan.py` (`TestScanDesignOutput`):
- `test_clean_output_passes`
- `test_script_tag_is_blocking`
- `test_blocking_flag_is_tagged_with_dotted_address`
- `test_blob_leaves_are_not_pattern_scanned`
- `test_prompt_injection_phrase_is_blocking`
- `test_banish_list_match_is_blocking`
- `test_non_allowlisted_url_is_external_but_not_blocking`
- `test_multi_file_container_aggregates_findings_across_leaves`

## Open questions

- `DesignEngine.generate()` itself never builds a multi-file `container` root or
  a `blob` root yet — no skill in `skills/builtins.py` currently sets
  `output_formats` to more than one format or `required_renderer` to a real
  value. Wiring an actual multi-file/rasterized skill through a renderer is
  follow-up work, not blocked by anything in this SPEC.
- `packages/maistro-design/src` is not part of CI's `mypy --strict` package list
  (pre-existing gap, unrelated to this change); the 7 pre-existing strict errors
  in this package are unchanged by this work.

## References

- `packages/maistro-design/src/maistro_design/types.py`
- `packages/maistro-design/src/maistro_design/scan.py`
- `packages/maistro-design/src/maistro_design/engine.py`
- `packages/maistro-design/src/maistro_design/protocols.py`
- `packages/maistro-design/src/maistro_design/systems/importer.py`
- `packages/maistro-design/tests/test_design.py`
- `packages/maistro-design/tests/test_scan.py`
- `docs/adr/ADR-062326-702b-multi-modality-design-outputs-hierarchical-artifact-containers.md`
