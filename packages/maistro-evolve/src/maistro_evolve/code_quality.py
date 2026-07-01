"""Objective code-quality scoring from ruff + bandit + radon.

Benchmark scoring for *code* has leaned on keyword matching and an LLM judge —
subjective and expensive. This module adds an objective, graded signal by
running three static tools and normalising each to 0..1:

  - **ruff**   — lint/style/correctness violations (fewer is better)
  - **bandit** — security issues, weighted by severity (fewer/lower is better)
  - **radon**  — cyclomatic complexity (lower) + maintainability index (higher)

The tools run as subprocesses (``python -m ruff|bandit|radon``), so this module
has no import-time dependency on them; a tool that isn't installed or errors is
dropped from the composite and the remaining weights renormalise (with a flag in
``tools_missing``), rather than silently scoring 0 or crashing. Use it two ways:
score the *quality of code an agent generates* (step-1 benchmark fitness) or the
*delta* on a self-modification to the codebase (step-2 code-level RSI gate).
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class QualityWeights:
    ruff: float = 0.25
    bandit: float = 0.25
    mypy: float = 0.20
    radon_cc: float = 0.15
    radon_mi: float = 0.15


@dataclass
class CodeQualityScore:
    composite: float
    ruff: float | None = None
    bandit: float | None = None
    mypy: float | None = None
    radon_cc: float | None = None
    radon_mi: float | None = None
    ruff_violations: int = 0
    bandit_issues: int = 0
    mypy_errors: int = 0
    avg_complexity: float = 0.0
    maintainability: float = 0.0
    tools_missing: list[str] = field(default_factory=list)


def _run_tool(args: list[str]) -> tuple[str, bool]:
    """Run ``python -m <args>``; return (stdout, available). available=False when
    the tool isn't installed, so callers can drop it instead of scoring it 0."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", *args],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "", False
    if "No module named" in proc.stderr:
        return "", False
    return proc.stdout, True


def _ruff(path: Path) -> tuple[float | None, int]:
    out, ok = _run_tool(["ruff", "check", "--output-format", "json", str(path)])
    if not ok:
        return None, 0
    try:
        violations = len(json.loads(out or "[]"))
    except json.JSONDecodeError:
        violations = 0
    return 1.0 / (1.0 + violations), violations


def _bandit(path: Path) -> tuple[float | None, int]:
    out, ok = _run_tool(["bandit", "-f", "json", "-q", str(path)])
    if not ok:
        return None, 0
    try:
        results = json.loads(out or "{}").get("results", [])
    except json.JSONDecodeError:
        results = []
    severity_weight = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    weighted = sum(severity_weight.get(r.get("issue_severity", "LOW"), 1) for r in results)
    return 1.0 / (1.0 + weighted), len(results)


def _mypy(path: Path) -> tuple[float | None, int]:
    # --ignore-missing-imports: don't penalise a snippet for deps it can't
    #   resolve; we're scoring the code's own type-consistency.
    # --config-file os.devnull: ignore the repo's pyproject mypy config (its
    #   pydantic plugin etc.), which would otherwise fail to import in a bare
    #   scoring env and looks like "tool missing".
    out, ok = _run_tool(
        [
            "mypy",
            "--ignore-missing-imports",
            "--no-error-summary",
            "--no-color-output",
            "--config-file",
            os.devnull,
            str(path),
        ]
    )
    if not ok:
        return None, 0
    errors = sum(1 for line in out.splitlines() if ": error:" in line)
    return 1.0 / (1.0 + errors), errors


def _radon(path: Path) -> tuple[float | None, float | None, float, float]:
    cc_out, cc_ok = _run_tool(["radon", "cc", "-j", str(path)])
    mi_out, mi_ok = _run_tool(["radon", "mi", "-j", str(path)])
    avg_cc = 0.0
    cc_score: float | None = None
    if cc_ok:
        try:
            cc_data = json.loads(cc_out or "{}")
            ccs = [b["complexity"] for blocks in cc_data.values() for b in blocks]
            avg_cc = statistics.mean(ccs) if ccs else 1.0
            # A-grade (avg CC <= 5) is perfect; decays toward 0 by CC ~25.
            cc_score = 1.0 if avg_cc <= 5 else max(0.0, 1.0 - (avg_cc - 5) / 20)
        except (json.JSONDecodeError, KeyError):
            cc_score = None
    mi_raw = 0.0
    mi_score: float | None = None
    if mi_ok:
        try:
            mi_data = json.loads(mi_out or "{}")
            mis = [v["mi"] for v in mi_data.values() if isinstance(v, dict) and "mi" in v]
            mi_raw = statistics.mean(mis) if mis else 100.0
            mi_score = max(0.0, min(1.0, mi_raw / 100.0))
        except (json.JSONDecodeError, KeyError):
            mi_score = None
    return cc_score, mi_score, round(avg_cc, 2), round(mi_raw, 2)


def score_path(path: str | Path, weights: QualityWeights | None = None) -> CodeQualityScore:
    """Score one file (or a directory tree) for code quality in 0..1."""
    weights = weights or QualityWeights()
    p = Path(path)
    ruff_s, ruff_v = _ruff(p)
    bandit_s, bandit_n = _bandit(p)
    mypy_s, mypy_e = _mypy(p)
    cc_s, mi_s, avg_cc, mi_raw = _radon(p)

    parts: list[tuple[float, float]] = []  # (score, weight)
    missing: list[str] = []
    for name, score, weight in (
        ("ruff", ruff_s, weights.ruff),
        ("bandit", bandit_s, weights.bandit),
        ("mypy", mypy_s, weights.mypy),
        ("radon_cc", cc_s, weights.radon_cc),
        ("radon_mi", mi_s, weights.radon_mi),
    ):
        if score is None:
            missing.append(name)
        else:
            parts.append((score, weight))

    if parts:
        total_w = sum(w for _, w in parts)
        composite = sum(s * w for s, w in parts) / total_w if total_w else 0.0
    else:
        composite = 0.0

    return CodeQualityScore(
        composite=round(composite, 4),
        ruff=ruff_s,
        bandit=bandit_s,
        mypy=mypy_s,
        radon_cc=cc_s,
        radon_mi=mi_s,
        ruff_violations=ruff_v,
        bandit_issues=bandit_n,
        mypy_errors=mypy_e,
        avg_complexity=avg_cc,
        maintainability=mi_raw,
        tools_missing=missing,
    )


def score_source(code: str, weights: QualityWeights | None = None) -> CodeQualityScore:
    """Score a code *string* (e.g. an agent's generated fix) by writing it to a
    temp file first — this is the step-1 benchmark-fitness entry point."""
    with tempfile.TemporaryDirectory(prefix="maistro-qscore-") as tmp:
        f = Path(tmp) / "candidate.py"
        f.write_text(code, encoding="utf-8")
        return score_path(f, weights)
