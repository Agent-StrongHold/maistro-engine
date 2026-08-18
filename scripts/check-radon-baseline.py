#!/usr/bin/env python3
"""Run radon and require the reviewed complexity baseline to match exactly.

This is a monotonic ratchet, not a blanket suppression: quality/radon-baseline.json
records every currently-known C/D/E/F block by qualified name (not by line
number, so unrelated code motion doesn't trip the gate). CI fails when a block
is newly C-or-worse, when a baselined block gets more complex, or when a block
improves/disappears without shrinking the baseline in the same PR. The baseline
therefore cannot retain slack that a later regression could consume.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "quality" / "radon-baseline.json"
PASSING_RANKS = {"A", "B"}


@dataclass(frozen=True)
class Block:
    path: str
    line: int
    name: str
    classname: str | None
    rank: str
    complexity: int

    @property
    def key(self) -> str:
        qualified = f"{self.classname}.{self.name}" if self.classname else self.name
        return f"{self.path}::{qualified}"

    def render(self) -> str:
        return f"{self.path}:{self.line} {self.name} -> {self.rank} ({self.complexity})"


def _load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _flatten(path: str, items: list[dict[str, Any]]) -> list[Block]:
    # radon's per-file item list is already flat: a class's methods appear as
    # their own top-level "method" items (each carrying "classname"), in
    # addition to being nested under the class item's "methods" key. Only
    # walk the top-level list, or every method gets counted twice.
    blocks: list[Block] = []
    for item in items:
        classname = item["classname"] if item["type"] == "method" else None
        blocks.append(
            Block(path, item["lineno"], item["name"], classname, item["rank"], item["complexity"])
        )
    return blocks


def _run_radon(args: list[str]) -> list[Block]:
    cmd = [sys.executable, "-m", "radon", "cc", "-j", *args]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
    data = json.loads(proc.stdout)
    blocks: list[Block] = []
    for path, items in data.items():
        blocks.extend(_flatten(path, items))
    return blocks


def main(argv: list[str]) -> int:
    scan_args = argv or ["packages/maistro-core/src"]
    baseline = {entry["key"]: entry for entry in _load_baseline()["entries"]}

    blocks = _run_radon(scan_args)
    findings = [block for block in blocks if block.rank not in PASSING_RANKS]

    new_findings: list[Block] = []
    regressions: list[tuple[Block, int]] = []
    improvements: list[tuple[Block, int]] = []
    for block in findings:
        recorded = baseline.get(block.key)
        if recorded is None:
            new_findings.append(block)
        elif block.complexity > recorded["complexity"]:
            regressions.append((block, recorded["complexity"]))
        elif block.complexity < recorded["complexity"]:
            improvements.append((block, recorded["complexity"]))

    seen_keys = {block.key for block in findings}
    stale = [key for key in baseline if key not in seen_keys]

    print("radon baseline summary:")
    print(f"  current C/D/E/F blocks: {len(findings)}")
    print(f"  baseline entries: {len(baseline)}")
    print(f"  new (unbaselined) findings: {len(new_findings)}")
    print(f"  regressed (more complex than baseline) findings: {len(regressions)}")
    print(f"  improved (baseline must shrink) findings: {len(improvements)}")
    print(f"  stale baseline entries (must be pruned): {len(stale)}")

    if new_findings:
        print("\nNew complexity findings with no baseline entry:", file=sys.stderr)
        for block in new_findings[:50]:
            print(f"  {block.render()}", file=sys.stderr)
    if regressions:
        print("\nComplexity regressions vs. recorded baseline:", file=sys.stderr)
        for block, baseline_complexity in regressions[:50]:
            print(f"  {block.render()} (baseline: {baseline_complexity})", file=sys.stderr)
    if improvements:
        print("\nComplexity improvements not yet ratcheted into the baseline:", file=sys.stderr)
        for block, baseline_complexity in improvements[:50]:
            print(
                f"  {block.render()} (baseline: {baseline_complexity}; lower it to {block.complexity})",
                file=sys.stderr,
            )
    if stale:
        print("\nStale baseline entries that must be removed:", file=sys.stderr)
        for key in stale[:50]:
            print(f"  {key}", file=sys.stderr)

    if improvements or stale:
        print(
            "\nThe reviewed complexity baseline must shrink in the same PR as the improvement; "
            "retained slack could otherwise pay for a later regression.",
            file=sys.stderr,
        )

    return 1 if new_findings or regressions or improvements or stale else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
