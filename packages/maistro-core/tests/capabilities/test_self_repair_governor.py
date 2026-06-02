"""Safety governor — keeps the autonomous loop self-limiting (SPEC-188)."""

from __future__ import annotations

from maistro.capabilities.self_repair_governor import GovernorReason, SafetyGovernor


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, secs: float) -> None:
        self.t += secs


def test_allows_first_attempt() -> None:
    gov = SafetyGovernor(clock=_Clock())
    d = gov.allow("docker:a")
    assert d.allowed is True
    assert d.reason is GovernorReason.OK


def test_in_flight_guard_blocks_second_dispatch() -> None:
    gov = SafetyGovernor(clock=_Clock())
    gov.record_dispatch("docker:a")
    d = gov.allow("docker:a")
    assert d.allowed is False
    assert d.reason is GovernorReason.IN_FLIGHT


def test_cooldown_blocks_immediate_redispatch() -> None:
    clock = _Clock()
    gov = SafetyGovernor(clock=clock, cooldown_s=60)
    gov.record_dispatch("docker:a")
    gov.record_result("docker:a", recovered=True)
    assert gov.allow("docker:a").reason is GovernorReason.COOLDOWN
    clock.advance(61)
    assert gov.allow("docker:a").allowed is True


def test_attempt_budget_exhausted_within_window() -> None:
    clock = _Clock()
    # high flap threshold so only the budget rule fires
    gov = SafetyGovernor(clock=clock, budget=3, window_s=1800, cooldown_s=10, flap_threshold=99)
    for _ in range(3):
        assert gov.allow("docker:a").allowed is True
        gov.record_dispatch("docker:a")
        gov.record_result("docker:a", recovered=True)
        clock.advance(11)  # past cooldown, within window
    d = gov.allow("docker:a")
    assert d.allowed is False
    assert d.reason is GovernorReason.BUDGET


def test_budget_resets_after_window() -> None:
    clock = _Clock()
    gov = SafetyGovernor(clock=clock, budget=2, window_s=600, cooldown_s=10, flap_threshold=99)
    for _ in range(2):
        gov.record_dispatch("docker:a")
        gov.record_result("docker:a", recovered=True)
        clock.advance(11)
    assert gov.allow("docker:a").reason is GovernorReason.BUDGET
    clock.advance(601)  # window elapsed → attempts pruned
    assert gov.allow("docker:a").allowed is True


def test_flap_detection_stops_oscillating_resource() -> None:
    clock = _Clock()
    # high budget so only the flap rule fires
    gov = SafetyGovernor(clock=clock, budget=99, window_s=99999, cooldown_s=10, flap_threshold=2)
    for _ in range(3):  # fix → recover → break, three times
        assert gov.allow("docker:a").allowed is True
        gov.record_dispatch("docker:a")
        gov.record_result("docker:a", recovered=True)
        clock.advance(11)
    d = gov.allow("docker:a")
    assert d.allowed is False
    assert d.reason is GovernorReason.FLAP


def test_resources_are_tracked_independently() -> None:
    gov = SafetyGovernor(clock=_Clock())
    gov.record_dispatch("docker:a")
    assert gov.allow("docker:a").reason is GovernorReason.IN_FLIGHT
    assert gov.allow("docker:b").allowed is True


def test_record_result_clears_in_flight() -> None:
    clock = _Clock()
    gov = SafetyGovernor(clock=clock, cooldown_s=0)
    gov.record_dispatch("docker:a")
    gov.record_result("docker:a", recovered=True)
    assert gov.allow("docker:a").allowed is True
