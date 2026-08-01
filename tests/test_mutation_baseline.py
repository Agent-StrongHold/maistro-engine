"""Regression coverage for mutation-baseline bootstrap behavior."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_mutation_baseline.py"


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("_mutation_baseline", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        del sys.modules[spec.name]
        raise
    yield mod
    del sys.modules[spec.name]


def test_unbaselined_source_reports_without_enforcement_and_merges_candidate(
    module, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = tmp_path / "rows.jsonl"
    rows.write_text(
        json.dumps(
            [
                {"mutations": [{"module_path": "packages/example.py"}]},
                {"test_outcome": "survived"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"entries": {"packages/already-covered.py": {"kill_rate": 0.95}}}\n',
        encoding="utf-8",
    )

    assert module.main([str(rows), "--baseline", str(baseline)]) == 0
    assert "no entry" in capsys.readouterr().out

    assert module.main([str(rows), "--baseline", str(baseline), "--write-baseline"]) == 0
    assert set(json.loads(baseline.read_text(encoding="utf-8"))["entries"]) == {
        "packages/already-covered.py",
        "packages/example.py",
    }


def test_baselined_source_regression_fails(module, tmp_path: Path) -> None:
    rows = tmp_path / "rows.jsonl"
    rows.write_text(
        json.dumps(
            [
                {"mutations": [{"module_path": "packages/example.py"}]},
                {"test_outcome": "survived"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"entries": {"packages/example.py": {"kill_rate": 0.9}}}\n',
        encoding="utf-8",
    )

    assert module.main([str(rows), "--baseline", str(baseline)]) == 1
