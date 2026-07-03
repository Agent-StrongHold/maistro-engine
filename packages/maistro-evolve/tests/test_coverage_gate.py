"""Tests for the coverage gate/score (subprocess stubbed — no real test run)."""

from __future__ import annotations

import json

import maistro_evolve.coverage_gate as cg


def test_gate_fails_when_coverage_drops() -> None:
    g = cg.coverage_gate(80.0, 70.0)
    assert g.passed is False
    assert "70.0" in g.reason


def test_gate_passes_within_tolerance_or_improved() -> None:
    assert cg.coverage_gate(80.0, 79.7).passed is True  # within 0.5 tol
    assert cg.coverage_gate(80.0, 85.0).passed is True  # improved


def test_gate_not_enforced_when_coverage_unavailable() -> None:
    assert cg.coverage_gate(None, 80.0).passed is True
    assert cg.coverage_gate(80.0, None).passed is True


def test_coverage_signal_scores_the_delta_not_the_absolute() -> None:
    # Reward the direction of the move: flat is neutral, a gain trends to 1.0, a
    # drop toward 0.0 — so a restyle (flat) no longer scores the suite's standing
    # coverage like every other candidate.
    assert cg.coverage_signal(60.0, 60.0, 0.2).score == 0.5  # flat → neutral
    assert cg.coverage_signal(60.0, 61.0, 0.2).score == 0.75  # +1pp over a 2pp swing
    assert cg.coverage_signal(60.0, 75.0, 0.2).score == 1.0  # big gain → clamped 1.0
    assert cg.coverage_signal(60.0, 55.0, 0.2).score == 0.0  # drop → clamped 0.0
    s = cg.coverage_signal(60.0, 75.0, 0.2)
    assert "+15.0pp" in s.rationale
    assert s.detail["delta"] == 15.0


def test_measure_coverage_parses_totals(monkeypatch) -> None:
    class R:
        returncode = 0
        stdout = json.dumps({"totals": {"percent_covered": 87.5}})

    monkeypatch.setattr(cg.subprocess, "run", lambda *a, **k: R())
    assert cg.measure_coverage(".") == 87.5


def test_measure_coverage_none_on_unparseable(monkeypatch) -> None:
    class R:
        returncode = 0
        stdout = "not json at all"

    monkeypatch.setattr(cg.subprocess, "run", lambda *a, **k: R())
    assert cg.measure_coverage(".") is None
