"""Tests for event bus, triggers, and cross-service integrations."""

from __future__ import annotations

import pytest

from maistro.events.bus import (
    Event,
    EventBus,
    EventCategory,
    Trigger,
    TriggerCondition,
)
from maistro.events.recipes import (
    coinswarm_drawdown_alert,
    coinswarm_evolution_complete,
    coinswarm_fitness_alert,
    security_event_escalation,
)


class TestTriggerCondition:
    def test_eq(self):
        c = TriggerCondition(field="x", op="eq", value=5)
        assert c.matches({"x": 5})
        assert not c.matches({"x": 3})

    def test_gt(self):
        c = TriggerCondition(field="val", op="gt", value=0.5)
        assert c.matches({"val": 0.7})
        assert not c.matches({"val": 0.3})

    def test_lt(self):
        c = TriggerCondition(field="fitness", op="lt", value=0.3)
        assert c.matches({"fitness": 0.1})
        assert not c.matches({"fitness": 0.5})

    def test_contains(self):
        c = TriggerCondition(field="name", op="contains", value="agent")
        assert c.matches({"name": "my-agent-1"})
        assert not c.matches({"name": "swarm"})

    def test_missing_field(self):
        c = TriggerCondition(field="missing", op="eq", value="x")
        assert not c.matches({"other": "y"})


class TestTrigger:
    def test_matches_event_type(self):
        t = Trigger(event_types=["agent_fitness"])
        e = Event(event_type="agent_fitness")
        assert t.matches(e)

    def test_rejects_wrong_type(self):
        t = Trigger(event_types=["agent_fitness"])
        e = Event(event_type="drawdown")
        assert not t.matches(e)

    def test_matches_conditions(self):
        t = Trigger(
            event_types=["agent_fitness"],
            conditions=[TriggerCondition(field="fitness", op="lt", value=0.3)],
        )
        e = Event(event_type="agent_fitness", payload={"fitness": 0.1})
        assert t.matches(e)

    def test_rejects_conditions(self):
        t = Trigger(
            event_types=["agent_fitness"],
            conditions=[TriggerCondition(field="fitness", op="lt", value=0.3)],
        )
        e = Event(event_type="agent_fitness", payload={"fitness": 0.5})
        assert not t.matches(e)

    def test_disabled(self):
        t = Trigger(enabled=False)
        e = Event()
        assert not t.matches(e)

    def test_cooldown(self):
        import time

        t = Trigger(cooldown_seconds=100.0)
        t.last_fired = time.time()
        e = Event()
        assert not t.matches(e)


class TestEventBus:
    async def test_emit_no_triggers(self):
        bus = EventBus()
        fired = await bus.emit(Event(event_type="test"))
        assert fired == []

    async def test_emit_fires_trigger(self):
        bus = EventBus()
        results = []
        bus.add_trigger(
            Trigger(
                name="test",
                event_types=["test"],
                action_type="log",
            )
        )
        bus.register_handler("log", lambda t, e: _append(results, (t.name, e.event_type)))
        fired = await bus.emit(Event(event_type="test"))
        assert len(fired) == 1
        assert fired[0].fire_count == 1

    async def test_cooldown_prevents_refire(self):
        bus = EventBus()
        bus.add_trigger(
            Trigger(
                name="cd",
                event_types=["test"],
                action_type="log",
                cooldown_seconds=999,
            )
        )
        bus.register_handler("log", lambda t, e: None)
        await bus.emit(Event(event_type="test"))
        fired = await bus.emit(Event(event_type="test"))
        assert len(fired) == 0

    async def test_history(self):
        bus = EventBus()
        await bus.emit(Event(event_type="a", source="x"))
        await bus.emit(Event(event_type="b", source="y"))
        history = bus.get_history()
        assert len(history) == 2
        assert bus.get_history(source="x") == [history[0]]

    async def test_list_triggers(self):
        bus = EventBus()
        bus.add_trigger(Trigger(name="t1"))
        bus.add_trigger(Trigger(name="t2"))
        triggers = bus.list_triggers()
        assert len(triggers) == 2

    async def test_remove_trigger(self):
        bus = EventBus()
        t = Trigger(trigger_id="abc", name="t1")
        bus.add_trigger(t)
        bus.remove_trigger("abc")
        assert bus.list_triggers() == []

    async def test_subscriber(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda e: _append(received, e.event_type))
        await bus.emit(Event(event_type="hello"))
        assert received == ["hello"]


class TestRecipes:
    def test_coinswarm_fitness_alert(self):
        t = coinswarm_fitness_alert(fitness_threshold=0.3)
        assert t.event_types == ["agent_fitness"]
        assert t.conditions[0].field == "fitness"
        assert t.conditions[0].value == 0.3
        low_event = Event(event_type="agent_fitness", payload={"fitness": 0.1})
        high_event = Event(event_type="agent_fitness", payload={"fitness": 0.8})
        assert t.matches(low_event)
        assert not t.matches(high_event)

    def test_coinswarm_drawdown_alert(self):
        t = coinswarm_drawdown_alert(max_drawdown=0.15)
        assert t.event_types == ["drawdown"]
        bad = Event(event_type="drawdown", payload={"drawdown_pct": 0.20})
        good = Event(event_type="drawdown", payload={"drawdown_pct": 0.05})
        assert t.matches(bad)
        assert not t.matches(good)

    def test_evolution_complete(self):
        t = coinswarm_evolution_complete(ha_token="test")
        assert t.event_types == ["evolution_cycle_complete"]
        assert t.action_type == "ha"

    def test_security_escalation(self):
        t = security_event_escalation()
        high = Event(event_type="warden_block", payload={"severity": "high"})
        low = Event(event_type="warden_block", payload={"severity": "low"})
        assert t.matches(high)
        assert not t.matches(low)


class TestIntegrations:
    def test_ha_init(self):
        from maistro.integrations.home_assistant import HomeAssistantIntegration

        ha = HomeAssistantIntegration(url="http://ha:8123", token="abc")
        assert ha._url == "http://ha:8123"

    def test_coinswarm_init(self):
        from maistro.integrations.coinswarm import CoinSwarmIntegration

        cs = CoinSwarmIntegration(url="http://swarm:8080")
        assert cs._url == "http://swarm:8080"

    def test_turing_init(self):
        from maistro.integrations.turing import TuringIntegration

        t = TuringIntegration(chat_url="http://turing:9101")
        assert t._chat_url == "http://turing:9101"

    async def test_coinswarm_emit_without_bus(self):
        from maistro.integrations.coinswarm import CoinSwarmIntegration

        cs = CoinSwarmIntegration()
        await cs.emit_agent_fitness("agent-1")

    async def test_coinswarm_emit_with_bus(self):
        from maistro.integrations.coinswarm import CoinSwarmIntegration

        bus = EventBus()
        received = []
        bus.subscribe(lambda e: _append(received, e.event_type))
        cs = CoinSwarmIntegration(event_bus=bus)

    async def test_turing_handles_coinswarm_event(self):
        from maistro.integrations.turing import TuringIntegration

        t = TuringIntegration(chat_url="http://not-real:9101")
        event = Event(
            category=EventCategory.TRADING,
            event_type="evolution_cycle_complete",
            source="coinswarm",
            payload={"generation": 5, "best_fitness": 0.85},
        )


def _append(lst, val):
    lst.append(val)
