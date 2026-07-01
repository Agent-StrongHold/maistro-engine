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


def test_coverage_signal_scores_absolute_with_delta() -> None:
    s = cg.coverage_signal(60.0, 75.0, 0.2)
    assert abs(s.score - 0.75) < 1e-9
    assert "+15.0" in s.rationale
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
