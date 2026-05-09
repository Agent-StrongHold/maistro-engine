"""Canvas layer model — ADR-039.

Adds a typed scene-graph layer model on top of the existing
`maistro_canvas.types` primitives:

- `LayerKind`        — 7-kind taxonomy (BACKGROUND/STRUCTURE/VEHICLE/PROP/
                       CHARACTER/FX/TEXT). Replaces the older `LayerType`,
                       which is kept as a deprecated alias.
- `Anchor`           — small subset of anchors (ground, horizon, floating).
                       Most attachment moves to `parent_id + parent_socket`.
- `Slot`             — normalised rectangular bounding hint.
- `Socket`           — named attachment point on an `AssetDefinition`.
- `OcclusionHint`    — typed in-front-of / behind constraints between
                       sibling instances.
- `GroundPlane`      — horizon + perspective on a `BackgroundComposition`.
- `BackgroundComposition` — sky / mid / foreground triplet plus ground
                       plane.
- `PersonalizationSlot` + `ChildProfile` — declarative personalisation
                       intent that compiles to a skin binding at render
                       time.
- `AssetSheet`       — generalised reference sheet for any named asset.
- `AssetDefinition`  — kind + base prompt + sheet + sockets + skin set
                       + default style. Either registered (named,
                       reusable) or inline (anonymous, one-off).
- `AssetInstance`    — placement of a definition on a canvas. Carries
                       parent_id + parent_socket, transform, slot,
                       anchor, occlusion, personalisation, skin binding,
                       prompt nudge, history.
- `WorldStyle`, `WorldStylePartial`, `RenderStyle`, `StyleVolume` —
                       book-level world style with per-image overrides
                       and page-range volumes (dream sequences,
                       flashbacks).
- `FoundationFootprint`, `WheelAnchors`, `CharacterPose` — pose
                       geometry discriminated by `LayerKind`.
- `Transform`        — 2D transform on an `AssetInstance`.

This module is types-only; behaviour (compositing, scene-graph walking,
asset-sheet generation) lands with the implementation ADRs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from maistro_canvas.types import LayerType

# ─────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────


class LayerKind(StrEnum):
    """Per ADR-039 §1. Pragmatic 7-kind split."""

    BACKGROUND = "background"
    STRUCTURE = "structure"
    VEHICLE = "vehicle"
    PROP = "prop"
    CHARACTER = "character"
    FX = "fx"
    TEXT = "text"


class Anchor(StrEnum):
    """Per ADR-039 §2. Small set; everything else is parent_id + socket."""

    GROUND_CONTACT = "ground_contact"
    HORIZON = "horizon"
    FLOATING = "floating"


# Migration map for the old `LayerType`. Per ADR-039 §1.
_LAYER_TYPE_TO_KIND: dict[str, LayerKind] = {
    LayerType.BACKGROUND: LayerKind.BACKGROUND,
    LayerType.CHARACTER: LayerKind.CHARACTER,
    # OBJECT defaults to PROP. STRUCTURE promotion requires an explicit
    # `metadata.role: "structure"` flag and human review.
    LayerType.OBJECT: LayerKind.PROP,
    LayerType.TEXT: LayerKind.TEXT,
}


def layer_type_to_kind(layer_type: str) -> LayerKind:
    """Map a legacy `LayerType` string to the new `LayerKind`."""
    try:
        return _LAYER_TYPE_TO_KIND[layer_type]
    except KeyError as exc:
        msg = f"Unknown LayerType: {layer_type!r}"
        raise ValueError(msg) from exc


# ─────────────────────────────────────────────────────────────────────
# Geometry value objects
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Slot:
    """Rectangular bounding hint, normalised 0..1."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Socket:
    """Named attachment point on an AssetDefinition."""

    name: str
    x: float
    y: float
    role: str | None = None


@dataclass(frozen=True)
class OcclusionHint:
    """Typed in-front-of / behind constraints between sibling instances.

    References are `instance_id` strings on the same canvas. The
    compositor resolves these to a topological z-order at render time.
    Cycles raise `OcclusionCycleError`.
    """

    in_front_of: tuple[str, ...] = ()
    behind: tuple[str, ...] = ()


@dataclass(frozen=True)
class Transform:
    """2D transform on an `AssetInstance`. Local to the parent if any."""

    tx: float = 0.0
    ty: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    rotation: float = 0.0


@dataclass(frozen=True)
class GroundPlane:
    """Horizon + perspective. Lives on a `BackgroundComposition`."""

    horizon_y: float
    vanishing_x: float | None = None
    perspective: Literal["flat", "one_point", "two_point", "isometric"] = "flat"


@dataclass(frozen=True)
class BackgroundComposition:
    """Layered background carrying sky / mid / foreground sub-images
    plus a typed ground plane other layers can anchor against."""

    ground_plane: GroundPlane
    sky: str | None = None
    mid: str | None = None
    foreground: str | None = None


# ─────────────────────────────────────────────────────────────────────
# Pose geometry, discriminated by kind (ADR-039 §8)
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FoundationFootprint:
    """Where a STRUCTURE meets the ground. Polygon, normalised 0..1."""

    polygon: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class WheelAnchors:
    """Where a VEHICLE contacts the ground. Wheel/keel/landing points."""

    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class CharacterPose:
    """Named bone positions for a CHARACTER layer."""

    bones: dict[str, tuple[float, float]]
    facial_keypoints: dict[str, tuple[float, float]] | None = None


PoseGeometry = FoundationFootprint | WheelAnchors | CharacterPose


# Mapping of which pose-geometry shape is allowed per LayerKind.
# PROP, FX, BACKGROUND, TEXT reject pose geometry.
POSE_GEOMETRY_FOR_KIND: dict[LayerKind, type] = {
    LayerKind.STRUCTURE: FoundationFootprint,
    LayerKind.VEHICLE: WheelAnchors,
    LayerKind.CHARACTER: CharacterPose,
}


# ─────────────────────────────────────────────────────────────────────
# Personalisation (ADR-039 §5)
# ─────────────────────────────────────────────────────────────────────


PersonalizationKind = Literal[
    "child_name",
    "child_likeness",
    "companion",
    "pet",
    "gift",
    "place_name",
    "pronouns",
]


@dataclass(frozen=True)
class PersonalizationSlot:
    """Declarative personalisation intent.

    `kind` says what role this slot plays in the book; `binding` is the
    key into `ChildProfile` / `BookVariables` that populates it. At
    render time the engine compiles this into a `skin_binding` on the
    parent `AssetDefinition`'s `skin_set`.
    """

    kind: PersonalizationKind
    binding: str


@dataclass(frozen=True)
class ChildProfile:
    """The personalisation key for a book render.

    `accommodations` follows the storybook-series shape from the design
    bundle — fidget, headphones, AAC tablet, comfort objects — so the
    art can include them when the parent wants them visible.
    """

    profile_id: str
    name: str
    pronouns: str | None = None
    likeness_refs: tuple[str, ...] = ()
    accommodations: tuple[str, ...] = ()
    age_range: str | None = None
    reading_level: str | None = None


# ─────────────────────────────────────────────────────────────────────
# Asset model — definition / instance split with inline support
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AssetSheet:
    """Generalised reference sheet for any named asset.

    v1 retains the existing 3-5 refs → IP-Adapter / FaceID conditioning →
    multi-pose sheet workflow that today serves only characters,
    extending it to any asset with a stable `asset_id`. A per-asset
    LoRA fine-tune is an opt-in `revision` graduation when sample count
    permits.
    """

    asset_id: str
    refs: tuple[str, ...]
    sheet_image: str
    revision: int = 1
    generation_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldStylePartial:
    """Sparse override; any field None inherits from the parent."""

    era: str | None = None
    realism: Literal["cel", "painterly", "watercolor", "photoreal", "line"] | None = None
    architectural_register: str | None = None
    vehicle_register: str | None = None
    palette_anchors: tuple[str, ...] | None = None
    fauna_realism: Literal["cute", "realistic"] | None = None


@dataclass(frozen=True)
class AssetDefinition:
    """Per ADR-039 §3. Either registered (named, reusable) or inline.

    For inline anonymous use, `asset_id` may be empty; the definition
    travels embedded inside the `AssetInstance`. The agent may promote
    an inline definition to a registered one when reuse is detected.
    """

    asset_id: str  # empty string allowed for inline definitions
    kind: LayerKind
    base_prompt: str
    asset_sheet: AssetSheet | None = None
    sockets: tuple[Socket, ...] = ()
    skin_set: dict[str, tuple[str, ...]] | None = None
    default_world_style: WorldStylePartial | None = None
    pose_geometry: PoseGeometry | None = None


@dataclass
class AssetInstance:
    """Per ADR-039 §3. Placement of a definition on a canvas.

    `definition` is either a registry id (`str`) or an inline
    `AssetDefinition` object. Scene-graph parenting via `parent_id` +
    `parent_socket`. `history` mirrors the POC's per-layer version
    history (frontend SPEC).
    """

    instance_id: str
    canvas_id: str
    definition: AssetDefinition | str
    parent_id: str | None = None
    parent_socket: str | None = None
    transform: Transform = field(default_factory=Transform)
    slot: Slot | None = None
    anchor: Anchor | None = None
    occlusion: OcclusionHint = field(default_factory=OcclusionHint)
    personalization: PersonalizationSlot | None = None
    skin_binding: dict[str, str] | None = None
    prompt_nudge: str | None = None
    visible: bool = True
    locked: bool = False
    history: tuple[str, ...] = ()
    z_index: int = 0


# ─────────────────────────────────────────────────────────────────────
# World style + render style + style volumes (ADR-039 §6)
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorldStyle:
    """Book-level world style. Bound once to the book, applied to every
    generation unless a `StyleVolume` overrides for a page range."""

    era: str
    realism: Literal["cel", "painterly", "watercolor", "photoreal", "line"]
    architectural_register: str
    vehicle_register: str
    palette_anchors: tuple[str, ...]
    fauna_realism: Literal["cute", "realistic"]


@dataclass(frozen=True)
class RenderStyle:
    """Per-image overrides applied above WorldStyle."""

    style_token: str | None = None
    palette_override: tuple[str, ...] | None = None
    line_weight: float | None = None


@dataclass(frozen=True)
class StyleVolume:
    """Page-range world-style override. Models dream sequences, flashbacks.

    `page_range` is inclusive. `partial_world_style` and
    `partial_render_style` are sparse; setting `era="dream"` does not
    imply any other field.
    """

    page_range: tuple[int, int]
    partial_world_style: WorldStylePartial | None = None
    partial_render_style: RenderStyle | None = None


def merge_world_style(
    base: WorldStyle,
    *partials: WorldStylePartial | None,
) -> WorldStyle:
    """Compose `WorldStyle` with sparse partials, later wins.

    Per ADR-039 §6, the prompt-time composition is:
        WorldStyle ⊕ matching StyleVolume.partial ⊕ RenderStyle ⊕ layer
    This helper handles the WorldStyle ⊕ partials portion.
    """
    era = base.era
    realism = base.realism
    architectural_register = base.architectural_register
    vehicle_register = base.vehicle_register
    palette_anchors = base.palette_anchors
    fauna_realism = base.fauna_realism

    for p in partials:
        if p is None:
            continue
        if p.era is not None:
            era = p.era
        if p.realism is not None:
            realism = p.realism
        if p.architectural_register is not None:
            architectural_register = p.architectural_register
        if p.vehicle_register is not None:
            vehicle_register = p.vehicle_register
        if p.palette_anchors is not None:
            palette_anchors = p.palette_anchors
        if p.fauna_realism is not None:
            fauna_realism = p.fauna_realism

    return WorldStyle(
        era=era,
        realism=realism,
        architectural_register=architectural_register,
        vehicle_register=vehicle_register,
        palette_anchors=palette_anchors,
        fauna_realism=fauna_realism,
    )


__all__ = [
    "POSE_GEOMETRY_FOR_KIND",
    "Anchor",
    "AssetDefinition",
    "AssetInstance",
    "AssetSheet",
    "BackgroundComposition",
    "CharacterPose",
    "ChildProfile",
    "FoundationFootprint",
    "GroundPlane",
    "LayerKind",
    "OcclusionHint",
    "PersonalizationKind",
    "PersonalizationSlot",
    "PoseGeometry",
    "RenderStyle",
    "Slot",
    "Socket",
    "StyleVolume",
    "Transform",
    "WheelAnchors",
    "WorldStyle",
    "WorldStylePartial",
    "layer_type_to_kind",
    "merge_world_style",
]
