"""Tests for task checkpoint replay and crash-loop quarantine (SPEC-256 / ADR-056)."""

from __future__ import annotations

from datetime import datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from maistro.agents.circuit_breaker import CircuitBreaker
from maistro.tasks.checkpoint import CheckpointKind, TaskCheckpoint
from maistro.tasks.recovery import CrashLoopPolicy, version_compatible
from maistro.tasks.replay import replay


def _checkpoint(
    sequence: int,
    kind: CheckpointKind,
    payload: dict,
    *,
    recipe_version: str = "v1",
    code_registry_version: str = "v1",
) -> TaskCheckpoint:
    return TaskCheckpoint(
        task_id="t1",
        sequence=sequence,
        kind=kind,
        payload=payload,
        recipe_version=recipe_version,
        code_registry_version=code_registry_version,
        created_at=datetime(2026, 6, 20) + timedelta(seconds=sequence),
    )


class TestToolCallReplay:
    def test_matched_pair_not_open(self) -> None:
        checkpoints = (
            _checkpoint(1, CheckpointKind.TOOL_CALL_ABOUT_TO_FIRE, {"call_id": "c1"}),
            _checkpoint(2, CheckpointKind.TOOL_CALL_DONE, {"call_id": "c1"}),
        )
        state = replay(checkpoints)
        assert state.open_tool_calls == frozenset()

    def test_unmatched_about_to_fire_is_open(self) -> None:
        checkpoints = (_checkpoint(1, CheckpointKind.TOOL_CALL_ABOUT_TO_FIRE, {"call_id": "c1"}),)
        state = replay(checkpoints)
        assert state.open_tool_calls == frozenset({"c1"})


class TestWaveReplay:
    def test_fan_out_then_completed(self) -> None:
        checkpoints = (
            _checkpoint(1, CheckpointKind.WAVE_FAN_OUT, {"wave_id": "w1"}),
            _checkpoint(2, CheckpointKind.WAVE_COMPLETED, {"wave_id": "w1"}),
        )
        state = replay(checkpoints)
        assert state.wave_status == {"w1": "completed"}

    def test_fan_out_alone_is_running(self) -> None:
        checkpoints = (_checkpoint(1, CheckpointKind.WAVE_FAN_OUT, {"wave_id": "w1"}),)
        state = replay(checkpoints)
        assert state.wave_status == {"w1": "running"}

    def test_wave_failed(self) -> None:
        checkpoints = (
            _checkpoint(1, CheckpointKind.WAVE_FAN_OUT, {"wave_id": "w1"}),
            _checkpoint(2, CheckpointKind.WAVE_FAILED, {"wave_id": "w1"}),
        )
        state = replay(checkpoints)
        assert state.wave_status == {"w1": "failed"}


class TestApprovalGateReplay:
    def test_raised_then_answered_not_pending(self) -> None:
        checkpoints = (
            _checkpoint(1, CheckpointKind.APPROVAL_GATE_RAISED, {"gate_id": "g1"}),
            _checkpoint(2, CheckpointKind.APPROVAL_GATE_ANSWERED, {"gate_id": "g1"}),
        )
        state = replay(checkpoints)
        assert state.pending_approval_gates == frozenset()

    def test_raised_alone_is_pending(self) -> None:
        checkpoints = (_checkpoint(1, CheckpointKind.APPROVAL_GATE_RAISED, {"gate_id": "g1"}),)
        state = replay(checkpoints)
        assert state.pending_approval_gates == frozenset({"g1"})


class TestSpendReplay:
    def test_spend_accumulates(self) -> None:
        checkpoints = (
            _checkpoint(1, CheckpointKind.SPEND_UPDATE, {"delta": 1.5}),
            _checkpoint(2, CheckpointKind.SPEND_UPDATE, {"delta": 2.5}),
        )
        state = replay(checkpoints)
        assert state.cumulative_spend == 4.0


class TestEmptyAndOrdering:
    def test_empty_sequence(self) -> None:
        state = replay(())
        assert state.open_tool_calls == frozenset()
        assert state.wave_status == {}
        assert state.cumulative_spend == 0.0
        assert state.pending_approval_gates == frozenset()

    def test_out_of_order_input_replayed_by_sequence(self) -> None:
        checkpoints = (
            _checkpoint(2, CheckpointKind.TOOL_CALL_DONE, {"call_id": "c1"}),
            _checkpoint(1, CheckpointKind.TOOL_CALL_ABOUT_TO_FIRE, {"call_id": "c1"}),
        )
        state = replay(checkpoints)
        assert state.open_tool_calls == frozenset()


class TestCrashLoopPolicy:
    def test_does_not_quarantine_below_threshold(self) -> None:
        breaker = CircuitBreaker(failure_threshold=5, name="task-crash")
        policy = CrashLoopPolicy()
        for _ in range(4):
            policy.record_crash(breaker)
        assert policy.should_quarantine(breaker) is False

    def test_quarantines_at_threshold(self) -> None:
        breaker = CircuitBreaker(failure_threshold=5, name="task-crash")
        policy = CrashLoopPolicy()
        for _ in range(5):
            policy.record_crash(breaker)
        assert policy.should_quarantine(breaker) is True


class TestVersionCompatible:
    def test_matching_versions_compatible(self) -> None:
        checkpoint = _checkpoint(
            1,
            CheckpointKind.SPEND_UPDATE,
            {"delta": 1.0},
            recipe_version="v2",
            code_registry_version="v3",
        )
        assert (
            version_compatible(
                checkpoint, current_recipe_version="v2", current_code_registry_version="v3"
            )
            is True
        )

    def test_recipe_version_drift_incompatible(self) -> None:
        checkpoint = _checkpoint(
            1,
            CheckpointKind.SPEND_UPDATE,
            {"delta": 1.0},
            recipe_version="v2",
            code_registry_version="v3",
        )
        assert (
            version_compatible(
                checkpoint, current_recipe_version="v9", current_code_registry_version="v3"
            )
            is False
        )

    def test_code_registry_version_drift_incompatible(self) -> None:
        checkpoint = _checkpoint(
            1,
            CheckpointKind.SPEND_UPDATE,
            {"delta": 1.0},
            recipe_version="v2",
            code_registry_version="v3",
        )
        assert (
            version_compatible(
                checkpoint, current_recipe_version="v2", current_code_registry_version="v9"
            )
            is False
        )


@given(n_pairs=st.integers(min_value=0, max_value=10))
def test_well_formed_pairs_never_left_open(n_pairs: int) -> None:
    checkpoints = []
    seq = 0
    for i in range(n_pairs):
        seq += 1
        checkpoints.append(
            _checkpoint(seq, CheckpointKind.TOOL_CALL_ABOUT_TO_FIRE, {"call_id": f"c{i}"})
        )
        seq += 1
        checkpoints.append(_checkpoint(seq, CheckpointKind.TOOL_CALL_DONE, {"call_id": f"c{i}"}))
        seq += 1
        checkpoints.append(
            _checkpoint(seq, CheckpointKind.APPROVAL_GATE_RAISED, {"gate_id": f"g{i}"})
        )
        seq += 1
        checkpoints.append(
            _checkpoint(seq, CheckpointKind.APPROVAL_GATE_ANSWERED, {"gate_id": f"g{i}"})
        )
    state = replay(tuple(checkpoints))
    assert state.open_tool_calls == frozenset()
    assert state.pending_approval_gates == frozenset()
