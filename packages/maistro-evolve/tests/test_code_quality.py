"""Composition/normalisation tests for the code-quality composite.

The tool subprocesses (ruff/bandit/mypy/radon) are stubbed, so these run
deterministically without the tools installed — they exercise the weighting,
missing-tool renormalisation, and score plumbing, not the tools themselves.
"""

from __future__ import annotations

from pathlib import Path

import maistro_evolve.code_quality as cq


def _stub(monkeypatch, *, ruff, bandit, mypy, radon):
    monkeypatch.setattr(cq, "_ruff", lambda p: ruff)
    monkeypatch.setattr(cq, "_bandit", lambda p: bandit)
    monkeypatch.setattr(cq, "_mypy", lambda p: mypy)
    monkeypatch.setattr(cq, "_radon", lambda p: radon)


def test_perfect_code_scores_one(monkeypatch, tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("x = 1\n")
    _stub(monkeypatch, ruff=(1.0, 0), bandit=(1.0, 0), mypy=(1.0, 0), radon=(1.0, 1.0, 1.0, 100.0))
    assert cq.score_path(f).composite == 1.0


def test_bad_code_scores_low(monkeypatch, tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("x = 1\n")
    _stub(monkeypatch, ruff=(0.1, 9), bandit=(0.2, 3), mypy=(0.5, 1), radon=(0.7, 0.6, 12.0, 60.0))
    s = cq.score_path(f)
    assert s.composite < 0.6
    assert s.bandit_issues == 3
    assert s.ruff_violations == 9


def test_missing_tool_renormalises_weights(monkeypatch, tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("x = 1\n")
    # mypy unavailable -> dropped; composite is the mean of the rest (all 1.0).
    _stub(monkeypatch, ruff=(1.0, 0), bandit=(1.0, 0), mypy=(None, 0), radon=(1.0, 1.0, 1.0, 100.0))
    s = cq.score_path(f)
    assert s.composite == 1.0
    assert "mypy" in s.tools_missing
    assert s.mypy is None


def test_all_tools_missing_scores_zero(monkeypatch, tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("x = 1\n")
    _stub(
        monkeypatch,
        ruff=(None, 0),
        bandit=(None, 0),
        mypy=(None, 0),
        radon=(None, None, 0.0, 0.0),
    )
    s = cq.score_path(f)
    assert s.composite == 0.0
    assert set(s.tools_missing) == {"ruff", "bandit", "mypy", "radon_cc", "radon_mi"}
