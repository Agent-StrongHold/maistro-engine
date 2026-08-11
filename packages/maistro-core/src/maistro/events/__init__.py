"""Event bus for cross-service communication, plus the durable event log,
trigger store, and idempotent processing loop (ADR-086)."""

from maistro.events.bus import (
    ActionHandler,
    Event,
    EventBus,
    EventCategory,
    Trigger,
    TriggerCondition,
    get_event_bus,
)
from maistro.events.durable_log import (
    EventLogStore,
    InMemoryEventLog,
    LoggedEvent,
    SqliteEventLog,
    append_from_bus_event,
)
from maistro.events.invocations import (
    MAX_ATTEMPTS,
    HandlerInvocation,
    InMemoryInvocationStore,
    InvocationStatus,
    InvocationStore,
    SqliteInvocationStore,
)
from maistro.events.processing import (
    HANDLER_FAILED_EVENT,
    HandlerCaller,
    HandlerCallError,
    HTTPHandlerCaller,
    process_events,
)
from maistro.events.trigger_store import (
    InMemoryTriggerStore,
    SqliteTriggerStore,
    TriggerDefinition,
    TriggerStore,
    pattern_matches,
)

__all__ = [
    "HANDLER_FAILED_EVENT",
    "MAX_ATTEMPTS",
    "ActionHandler",
    "Event",
    "EventBus",
    "EventCategory",
    "EventLogStore",
    "HTTPHandlerCaller",
    "HandlerCallError",
    "HandlerCaller",
    "HandlerInvocation",
    "InMemoryEventLog",
    "InMemoryInvocationStore",
    "InMemoryTriggerStore",
    "InvocationStatus",
    "InvocationStore",
    "LoggedEvent",
    "SqliteEventLog",
    "SqliteInvocationStore",
    "SqliteTriggerStore",
    "Trigger",
    "TriggerCondition",
    "TriggerDefinition",
    "TriggerStore",
    "append_from_bus_event",
    "get_event_bus",
    "pattern_matches",
    "process_events",
]
