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
from maistro.memory.learnings.extractor import ToolCorrectionExtractor
from maistro.memory.learnings.store import InMemoryLearningStore
from maistro.memory.outcomes import InMemoryOutcomeStore
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
    from maistro.protocols.memory import LearningStore, OutcomeStore, SessionStore
    from maistro.protocols.quota import QuotaTracker
    from maistro.security.sentinel.audit import AuditLog
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
    quota_tracker = InMemoryQuotaTracker()
    learning_store = InMemoryLearningStore()
    outcome_store = InMemoryOutcomeStore()
    session_store = InMemorySessionStore()

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
        audit_log=audit_log,
    )

    logger.info("Container wired (InMemory stores, no database)")
    return container
