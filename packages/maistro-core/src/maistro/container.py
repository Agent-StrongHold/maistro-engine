"""DI container: wires protocols to implementations.

The Container holds all wired dependencies and provides the main
request entry point via ``route_request()``.

The Conduit pipeline handles the actual request flow:
  classify → route → agent.handle → response
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maistro.agents.context_builder import ContextBuilder
from maistro.agents.intents import IntentRegistry, build_intent_registry
from maistro.classifier.engine import ClassifierEngine
from maistro.memory.context_assembly import DefaultContextAssemblyPolicy
from maistro.memory.episodic.store import InMemoryEpisodicStore
from maistro.memory.learnings.extractor import ToolCorrectionExtractor
from maistro.memory.learnings.store import InMemoryLearningStore
from maistro.memory.outcomes import InMemoryOutcomeStore
from maistro.projects.store import InMemoryProjectStore
from maistro.quota.tracker import InMemoryQuotaTracker
from maistro.router.selector import RouterEngine
from maistro.security.gate import Gate
from maistro.security.warden.detector import Warden
from maistro.sessions.store import InMemorySessionStore
from maistro.types.config import AgentConfig
from maistro.types.errors import ConfigError

if TYPE_CHECKING:
    from maistro.agents.base import Agent
    from maistro.capabilities.registry import CapabilityRegistry
    from maistro.projects.store import ProjectStore
    from maistro.protocols.memory import (
        ContextAssemblyPolicy,
        EpisodicStore,
        LearningStore,
        OutcomeStore,
        SessionStore,
    )
    from maistro.protocols.quota import QuotaTracker
    from maistro.security._types import AuditLog
    from maistro.security.sentinel.policy import Sentinel

logger = logging.getLogger("maistro.container")


@dataclass
class Container:
    """Holds all wired dependencies."""

    config: AgentConfig
    router: RouterEngine
    classifier: ClassifierEngine
    quota_tracker: QuotaTracker
    learning_store: LearningStore
    learning_extractor: ToolCorrectionExtractor
    outcome_store: OutcomeStore
    session_store: SessionStore
    warden: Warden
    gate: Gate
    sentinel: Sentinel
    context_builder: ContextBuilder
    intent_registry: IntentRegistry
    capabilities: CapabilityRegistry = None  # type: ignore[assignment]  # wired in create_container
    episodic_store: EpisodicStore = None  # type: ignore[assignment]  # wired in create_container
    project_store: ProjectStore = None  # type: ignore[assignment]  # wired in create_container
    context_assembly_policy: ContextAssemblyPolicy = None  # type: ignore[assignment]
    agents: dict[str, Agent] = field(default_factory=dict)
    audit_log: AuditLog | None = None
    conduit: Any = None
    db_pool: Any = None

    def __post_init__(self) -> None:
        if self.conduit is None:
            from maistro.conduit import Conduit as ConduitPipeline

            self.conduit = ConduitPipeline(self)
        if self.capabilities is None:
            from maistro.capabilities.bootstrap import default_capability_registry

            self.capabilities = default_capability_registry()

    async def route_request(
        self,
        messages: list[dict[str, Any]],
        *,
        auth: Any = None,
        session_id: str | None = None,
        intent_hint: str = "",
    ) -> dict[str, Any]:
        result: dict[str, Any] = await self.conduit.route_request(
            messages,
            auth=auth,
            session_id=session_id,
            intent_hint=intent_hint,
        )
        return result


async def create_container(config: AgentConfig) -> Container:
    """Wire all dependencies and create the container."""
    if not config.router_api_key:
        msg = "ROUTER_API_KEY is required."
        raise ConfigError(msg)

    warden = Warden()
    learning_extractor = ToolCorrectionExtractor()
    db_pool: Any = None
    if config.database_url.startswith("sqlite:"):
        (
            db_pool,
            quota_tracker,
            learning_store,
            outcome_store,
            session_store,
        ) = await _wire_sqlite_backend(config.database_url)
    else:
        quota_tracker = InMemoryQuotaTracker()
        learning_store = InMemoryLearningStore()
        outcome_store = InMemoryOutcomeStore()
        session_store = InMemorySessionStore()
    episodic_store = InMemoryEpisodicStore()
    project_store = InMemoryProjectStore()
    context_assembly_policy = DefaultContextAssemblyPolicy(
        episodic_store=episodic_store,
        outcome_store=outcome_store,
        project_store=project_store,
    )

    router = RouterEngine(quota_tracker)
    classifier = ClassifierEngine()
    context_builder = ContextBuilder()
    intent_registry = build_intent_registry()
    gate = Gate(warden=warden)

    from maistro.security._types import PermissionTable
    from maistro.security.sentinel.audit import InMemoryAuditLog
    from maistro.security.sentinel.policy import Sentinel

    audit_log = InMemoryAuditLog()
    permission_table: PermissionTable = {}
    sentinel = Sentinel(
        warden=warden,
        permission_table=permission_table,
        audit_log=audit_log,
    )

    from maistro.capabilities.bootstrap import default_capability_registry

    capabilities = default_capability_registry()

    container = Container(
        config=config,
        router=router,
        classifier=classifier,
        quota_tracker=quota_tracker,
        learning_store=learning_store,
        learning_extractor=learning_extractor,
        outcome_store=outcome_store,
        session_store=session_store,
        warden=warden,
        gate=gate,
        sentinel=sentinel,
        context_builder=context_builder,
        intent_registry=intent_registry,
        capabilities=capabilities,
        episodic_store=episodic_store,
        project_store=project_store,
        context_assembly_policy=context_assembly_policy,
        audit_log=audit_log,
        db_pool=db_pool,
    )

    backend = "SQLite" if db_pool is not None else "InMemory"
    logger.info("Container wired (%s stores)", backend)
    return container


async def _wire_sqlite_backend(
    database_url: str,
) -> tuple[
    Any,
    QuotaTracker,
    LearningStore,
    OutcomeStore,
    SessionStore,
]:
    """Open a SQLite connection and wire the homelab/single-instance stores.

    ``database_url`` of the form ``sqlite:///path/to/file.db`` (or
    ``sqlite://`` for an in-memory DB) selects this backend instead of the
    default in-memory stores — no Postgres server required.
    """
    import aiosqlite

    from maistro.persistence.sqlite_learnings import SqliteLearningStore
    from maistro.persistence.sqlite_outcomes import SqliteOutcomeStore
    from maistro.persistence.sqlite_quota import SqliteQuotaTracker
    from maistro.persistence.sqlite_sessions import SqliteSessionStore

    path = database_url.removeprefix("sqlite:///").removeprefix("sqlite://") or ":memory:"
    conn = await aiosqlite.connect(path)

    sqlite_quota_tracker = SqliteQuotaTracker(conn)
    sqlite_learning_store = SqliteLearningStore(conn)
    sqlite_outcome_store = SqliteOutcomeStore(conn)
    sqlite_session_store = SqliteSessionStore(conn)
    await sqlite_quota_tracker.ensure_schema()
    await sqlite_learning_store.ensure_schema()
    await sqlite_outcome_store.ensure_schema()
    await sqlite_session_store.ensure_schema()

    quota_tracker: QuotaTracker = sqlite_quota_tracker
    learning_store: LearningStore = sqlite_learning_store
    outcome_store: OutcomeStore = sqlite_outcome_store
    session_store: SessionStore = sqlite_session_store

    return conn, quota_tracker, learning_store, outcome_store, session_store
