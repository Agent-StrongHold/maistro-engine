"""maistro-design types: skills, design systems, projects, outputs, and domain errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from maistro.types.errors import AgentError

from maistro_design.trust import TrustTier


class SkillMode(StrEnum):
    PROTOTYPE = "prototype"
    DECK = "deck"
    TEMPLATE = "template"
    DESIGN_SYSTEM = "design-system"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class OutputFormat(StrEnum):
    HTML = "html"
    MARKDOWN = "markdown"
    PPTX = "pptx"
    PNG = "png"
    SVG = "svg"
    PDF = "pdf"
    CSS = "css"
    JSON = "json"


@dataclass(frozen=True)
class DiscoveryField:
    """One question in a skill's discovery form. Must be answered before generation."""

    key: str
    label: str
    description: str
    field_type: str = "text"            # text | select | multiselect | color | number
    options: tuple[str, ...] = ()
    required: bool = True
    default: str | None = None
    trust_tier: TrustTier = TrustTier.T3  # user-supplied fields default to untrusted

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "field_type": self.field_type,
            "options": list(self.options),
            "required": self.required,
            "default": self.default,
        }


@dataclass
class DesignSkill:
    """Composable design skill — the atomic unit of design capability.

    Mirrors open-design's SKILL.md concept, backed by maistro-core's trust-tier model.
    """

    slug: str                                       # kebab-case, e.g. "login-flow"
    name: str
    mode: SkillMode
    description: str
    discovery_form: list[DiscoveryField] = field(default_factory=list)
    system_prompt: str = ""
    compatible_design_systems: list[str] = field(default_factory=list)  # [] = all
    featured: bool = False
    trust_tier: TrustTier = TrustTier.T0
    output_formats: list[OutputFormat] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ColorToken:
    name: str
    value: str
    group: str = "brand"


@dataclass(frozen=True)
class TypographyToken:
    name: str
    family: str
    size: str
    weight: str = "400"
    line_height: str | None = None
    letter_spacing: str | None = None


@dataclass(frozen=True)
class SpacingToken:
    name: str
    value: str


@dataclass
class DesignSystem:
    """Brand/style specification — colors, typography, tokens, and design guidelines.

    Mirrors open-design's design-systems/{slug}/ folder (manifest.json + DESIGN.md + tokens.css).
    Built-in systems are TrustTier.T0; user-loaded systems default to TrustTier.T2.
    """

    slug: str
    name: str
    description: str
    colors: list[ColorToken] = field(default_factory=list)
    typography: list[TypographyToken] = field(default_factory=list)
    spacing: list[SpacingToken] = field(default_factory=list)
    tokens_css: str = ""
    design_md: str = ""
    components: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    trust_tier: TrustTier = TrustTier.T0

    def get_color(self, name: str) -> ColorToken | None:
        return next((c for c in self.colors if c.name == name), None)

    def get_typography(self, name: str) -> TypographyToken | None:
        return next((t for t in self.typography if t.name == name), None)


@dataclass
class DiscoveryResult:
    """Collected responses from a skill's discovery form."""

    skill_slug: str
    responses: dict[str, str]
    design_system_slug: str = "default"
    trust_tier: TrustTier = TrustTier.T3  # user-supplied, always starts untrusted
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DesignOutput:
    """A generated design artifact."""

    format: OutputFormat
    content: str
    url: str | None = None
    trust_tier: TrustTier = TrustTier.T3
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignProject:
    """Top-level design project combining skill + design system + outputs."""

    id: str
    name: str
    skill_slug: str
    design_system_slug: str
    trust_tier: TrustTier = TrustTier.T3
    canvas_id: str | None = None
    outputs: list[DesignOutput] = field(default_factory=list)
    discovery: DiscoveryResult | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "skill_slug": self.skill_slug,
            "design_system_slug": self.design_system_slug,
            "trust_tier": self.trust_tier,
            "canvas_id": self.canvas_id,
            "output_count": len(self.outputs),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ─── Domain errors ────────────────────────────────────────────────────────────


class DesignError(AgentError):
    code = "DESIGN_ERROR"


class SkillNotFoundError(DesignError):
    code = "SKILL_NOT_FOUND"


class DesignSystemNotFoundError(DesignError):
    code = "DESIGN_SYSTEM_NOT_FOUND"


class DiscoveryIncompleteError(DesignError):
    code = "DISCOVERY_INCOMPLETE"


class SkillModeError(DesignError):
    code = "SKILL_MODE_ERROR"


class DesignProjectNotFoundError(DesignError):
    code = "DESIGN_PROJECT_NOT_FOUND"


class IncompatibleDesignSystemError(DesignError):
    code = "INCOMPATIBLE_DESIGN_SYSTEM"


class TrustBannedError(DesignError):
    """Raised when a banish-list pattern is found in a discovery response."""

    code = "TRUST_BANNED"


class TrustUpgradeRequiredError(DesignError):
    """Raised when content requires admin approval before trust can be upgraded."""

    code = "TRUST_UPGRADE_REQUIRED"
