"""DesignService — singleton providing DesignEngine and PgDesignProjectStore.

Initializes maistro-design subsystems for the Conductor backend.
Wires the design engine (skill registry + system registry) and project
persistence store (PostgreSQL) as singletons accessible via get_design_engine()
and get_design_store().
"""

from __future__ import annotations

import functools
import logging
import os
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger("hive.design_service")

__all__ = [
    "get_design_engine",
    "get_design_store",
    "start_design_service",
    "stop_design_service",
]


@functools.lru_cache(maxsize=1)
def _get_async_engine() -> AsyncEngine | None:
    """Return an async SQLAlchemy engine for design projects, or None if DATABASE_URL is unset."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        logger.debug("DATABASE_URL not configured — design persistence disabled")
        return None
    try:
        return create_async_engine(url, pool_pre_ping=True)
    except Exception as exc:
        logger.warning("Failed to create design database engine: %s", exc)
        return None


@functools.lru_cache(maxsize=1)
def _get_async_session_factory() -> async_sessionmaker[Any] | None:
    """Return an async session factory for design projects, or None if no engine."""
    engine = _get_async_engine()
    if engine is None:
        return None
    return async_sessionmaker(engine, expire_on_commit=False)


_engine_singleton: Any = None
_store_singleton: Any = None


def get_design_engine() -> Any:
    """Get the DesignEngine singleton."""
    if _engine_singleton is None:
        raise RuntimeError(
            "DesignEngine not initialized — ensure start_design_service() was called in app lifespan"
        )
    return _engine_singleton


def get_design_store() -> Any:
    """Get the PgDesignProjectStore singleton."""
    if _store_singleton is None:
        raise RuntimeError(
            "DesignProjectStore not initialized — ensure start_design_service() was called in app lifespan"
        )
    return _store_singleton


async def start_design_service(settings: Settings) -> None:
    """Initialize the DesignEngine and PgDesignProjectStore singletons.

    Called during FastAPI lifespan startup.
    """
    global _engine_singleton, _store_singleton

    try:
        from maistro_design.engine import DesignEngine
        from maistro_design.skills.builtins import load_builtins
        from maistro_design.skills.registry import InMemoryDesignSkillRegistry
        from maistro_design.stores import PgDesignProjectStore
        from maistro_design.systems.registry import InMemoryDesignSystemRegistry
        from maistro_design.trust import TrustTier
        from maistro_design.types import DesignSystem

        # Initialize skill registry with built-in skills
        skill_registry = InMemoryDesignSkillRegistry()
        load_builtins(skill_registry)
        logger.info("Design skill registry initialized")

        # Initialize system registry with default system
        system_registry = InMemoryDesignSystemRegistry()
        system_registry.register(
            DesignSystem(
                slug="default",
                name="Default",
                description="Neutral default design system",
                trust_tier=TrustTier.T0,
            )
        )
        logger.info("Design system registry initialized")

        # Initialize project store if database is available
        project_store: Any | None = None
        session_factory = _get_async_session_factory()
        if session_factory is not None:
            project_store = PgDesignProjectStore(session_factory=session_factory)
            logger.info("Design project store initialized with PostgreSQL")
        else:
            logger.info("Design project store disabled (no DATABASE_URL configured)")

        # Initialize design engine with registries and optional store
        _engine_singleton = DesignEngine(
            skill_registry=skill_registry,
            system_registry=system_registry,
            project_store=project_store,
        )
        _store_singleton = project_store
        logger.info("DesignEngine initialized")

    except ImportError as exc:
        logger.warning("maistro-design not installed or unavailable: %s", exc)
    except Exception as exc:
        logger.warning("DesignService initialization failed: %s", exc, exc_info=True)


async def stop_design_service() -> None:
    """Cleanup the DesignService singletons."""
    global _engine_singleton, _store_singleton
    _engine_singleton = None
    _store_singleton = None
    _get_async_engine.cache_clear()
    _get_async_session_factory.cache_clear()
