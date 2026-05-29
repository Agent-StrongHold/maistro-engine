"""maistro-design — composable design skills + design systems + canvas engine.

Public API surface. Import from here for stable, ADR-058-governed access.
"""

from maistro_design.engine import DesignEngine
from maistro_design.protocols import (
    DesignEngineProtocol,
    DesignProjectStore,
    DesignSkillRegistry,
    DesignSystemRegistry,
)
from maistro_design.skills.builtins import load_builtins
from maistro_design.skills.registry import InMemoryDesignSkillRegistry
from maistro_design.systems.loader import DesignSystemLoader
from maistro_design.systems.registry import InMemoryDesignSystemRegistry
from maistro_design.trust import (
    InMemoryTrustBanishList,
    InMemoryTrustReviewQueue,
    TrustReviewRecord,
    TrustTier,
)
from maistro_design.types import (
    ColorToken,
    DesignError,
    DesignOutput,
    DesignProject,
    DesignSkill,
    DesignSystem,
    DesignSystemNotFoundError,
    DiscoveryField,
    DiscoveryIncompleteError,
    DiscoveryResult,
    IncompatibleDesignSystemError,
    OutputFormat,
    SkillMode,
    SkillModeError,
    SkillNotFoundError,
    SpacingToken,
    TrustBannedError,
    TrustUpgradeRequiredError,
    TypographyToken,
)

__all__ = [
    "ColorToken",
    "DesignEngine",
    "DesignEngineProtocol",
    "DesignError",
    "DesignOutput",
    "DesignProject",
    "DesignProjectStore",
    "DesignSkill",
    "DesignSkillRegistry",
    "DesignSystem",
    "DesignSystemLoader",
    "DesignSystemNotFoundError",
    "DesignSystemRegistry",
    "DiscoveryField",
    "DiscoveryIncompleteError",
    "DiscoveryResult",
    "InMemoryDesignSkillRegistry",
    "InMemoryDesignSystemRegistry",
    "InMemoryTrustBanishList",
    "InMemoryTrustReviewQueue",
    "IncompatibleDesignSystemError",
    "OutputFormat",
    "SkillMode",
    "SkillModeError",
    "SkillNotFoundError",
    "SpacingToken",
    "TrustBannedError",
    "TrustReviewRecord",
    "TrustTier",
    "TrustUpgradeRequiredError",
    "TypographyToken",
    "load_builtins",
]
