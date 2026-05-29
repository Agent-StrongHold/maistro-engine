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
    # Engine
    "DesignEngine",
    # Protocols
    "DesignEngineProtocol",
    "DesignProjectStore",
    "DesignSkillRegistry",
    "DesignSystemRegistry",
    # Registries
    "InMemoryDesignSkillRegistry",
    "InMemoryDesignSystemRegistry",
    # Loaders
    "DesignSystemLoader",
    "load_builtins",
    # Trust
    "TrustTier",
    "TrustReviewRecord",
    "InMemoryTrustBanishList",
    "InMemoryTrustReviewQueue",
    # Types
    "SkillMode",
    "OutputFormat",
    "DiscoveryField",
    "DesignSkill",
    "ColorToken",
    "TypographyToken",
    "SpacingToken",
    "DesignSystem",
    "DiscoveryResult",
    "DesignOutput",
    "DesignProject",
    # Errors
    "DesignError",
    "SkillNotFoundError",
    "DesignSystemNotFoundError",
    "DiscoveryIncompleteError",
    "SkillModeError",
    "IncompatibleDesignSystemError",
    "TrustBannedError",
    "TrustUpgradeRequiredError",
]
