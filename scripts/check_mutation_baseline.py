#!/usr/bin/env python3
"""Ratchet Cosmic Ray kill rates per production source file.

The committed baseline records the last reviewed full-codebase sweep. New files
must clear the floor; existing files must clear both the floor and their prior
rate. ``--write-baseline`` creates a candidate JSON file from a full sweep for
human review and commit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "quality" / "mutation-baseline.json"
FLOOR = 0.90


def scores(rows_path: Path) -> dict[str, tuple[int, int]]:
    """Return ``source -> (killed, total)`` from Cosmic Ray dump JSONL."""
    result: dict[str, list[int]] = {}
    for raw in rows_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        parsed = json.loads(raw)
        if not (isinstance(parsed, list) and len(parsed) == 2):
            continue
        work_item, outcome = parsed
        if not isinstance(work_item, dict) or not isinstance(outcome, dict):
            continue
        mutations = work_item.get("mutations") or []
        source = mutations[0].get("module_path") if mutations else None
        if not isinstance(source, str):
            continue
        killed, total = result.setdefault(source, [0, 0])
        result[source] = [killed + (outcome.get("test_outcome") == "killed"), total + 1]
    return {source: (values[0], values[1]) for source, values in result.items()}


def payload(current: dict[str, tuple[int, int]]) -> dict[str, Any]:
    return {
        "version": 1,
        "owner": "@BlakeMatthews-dev",
        "policy": (
            "Per-source mutation ratchet. New sources must meet the 90% floor; "
            "reviewed sources must not regress below their recorded kill rate."
        ),
        "entries": {
            source: {"killed": killed, "total": total, "kill_rate": round(killed / total, 4)}
            for source, (killed, total) in sorted(current.items())
            if total
        },
    }


def enforce(current: dict[str, tuple[int, int]], baseline: dict[str, Any]) -> list[str]:
    entries = baseline.get("entries", {})
    failures: list[str] = []
    for source, (killed, total) in sorted(current.items()):
        if total == 0:
            failures.append(f"{source}: no mutants produced")
            continue
        rate = killed / total
        prior = entries.get(source, {}).get("kill_rate", FLOOR)
        required = max(FLOOR, float(prior))
        if rate < required:
            failures.append(f"{source}: {rate:.1%} below required {required:.1%}")
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rows", type=Path, help="Cosmic Ray dump JSONL")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)
    current = scores(args.rows)
    if not current:
        print(
            "::error::No mutation outcomes found; this is a configuration failure.", file=sys.stderr
        )
        return 1
    if args.write_baseline:
        args.baseline.write_text(
            json.dumps(payload(current), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            f"wrote candidate mutation baseline for {len(current)} source file(s): {args.baseline}"
        )
        return 0
    if not args.baseline.is_file():
        print(f"::error::Missing mutation baseline: {args.baseline}", file=sys.stderr)
        return 1
    failures = enforce(current, json.loads(args.baseline.read_text(encoding="utf-8")))
    print(
        f"mutation baseline summary: {len(current)} source file(s), {len(failures)} regression(s)"
    )
    for failure in failures:
        print(f"::error::{failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
