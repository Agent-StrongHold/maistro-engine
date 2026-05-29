"""In-memory design skill registry — thread-safe, t0 skills are immutable."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from maistro_design.trust import TrustTier

if TYPE_CHECKING:
    from maistro_design.types import DesignSkill

logger = logging.getLogger("maistro.design.skills.registry")


class InMemoryDesignSkillRegistry:
    """Thread-safe in-memory registry for design skills.

    Built-in (T0) skills cannot be overwritten by community (T2+) installs.
    """

    def __init__(self) -> None:
        self._skills: dict[str, DesignSkill] = {}
        self._lock = threading.RLock()

    def register(self, skill: DesignSkill) -> None:
        key = skill.slug
        with self._lock:
            existing = self._skills.get(key)
            if (
                existing
                and existing.trust_tier == TrustTier.T0
                and skill.trust_tier != TrustTier.T0
            ):
                logger.warning("Blocked: cannot overwrite built-in skill '%s'", key)
                return
            self._skills[key] = skill
        logger.debug("Registered design skill: %s (mode=%s)", skill.slug, skill.mode)

    def get(self, slug: str) -> DesignSkill | None:
        return self._skills.get(slug)

    def list_all(self) -> list[DesignSkill]:
        return list(self._skills.values())

    def list_by_mode(self, mode: str) -> list[DesignSkill]:
        return [s for s in self._skills.values() if s.mode == mode]

    def list_featured(self) -> list[DesignSkill]:
        return [s for s in self._skills.values() if s.featured]

    def delete(self, slug: str) -> bool:
        with self._lock:
            if slug not in self._skills:
                return False
            del self._skills[slug]
        logger.debug("Deleted design skill: %s", slug)
        return True

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, slug: str) -> bool:
        return slug in self._skills
