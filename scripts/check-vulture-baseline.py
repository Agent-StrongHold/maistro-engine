#!/usr/bin/env python3
"""Run vulture and require exact reviewed finding identities.

Rules in quality/vulture-baseline.json explain why a finding is dynamically or
declaratively used. Each rule must also snapshot the stable identity multiset of
the findings it currently accepts. CI therefore fails when accepted debt grows,
shrinks, or is replaced by different debt without an explicit baseline update.
High-confidence unreachable code is never allowlisted.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "quality" / "vulture-baseline.json"
_FINDING_RE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+): (?P<message>.*?) \((?P<confidence>\d+)% confidence\)$"
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    message: str
    confidence: int

    @classmethod
    def parse(cls, line: str) -> Finding | None:
        match = _FINDING_RE.match(line.strip())
        if not match:
            return None
        return cls(
            path=match.group("path"),
            line=int(match.group("line")),
            message=match.group("message"),
            confidence=int(match.group("confidence")),
        )

    @property
    def stable_key(self) -> str:
        """Identity that survives unrelated line movement while retaining symbol identity."""
        return f"{self.path}::{self.message}"

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message} ({self.confidence}% confidence)"


@dataclass(frozen=True)
class Classification:
    by_rule: dict[str, list[Finding]]
    unclassified: list[Finding]
    never_allowlist: list[Finding]


@dataclass(frozen=True)
class SnapshotDelta:
    rule_id: str
    added: list[str]
    removed: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def _load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _source_for(path: str) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _matches_rule(finding: Finding, rule: dict[str, Any]) -> bool:
    path_regex = rule.get("path_regex")
    if path_regex and not re.search(str(path_regex), finding.path):
        return False

    message_regex = rule.get("message_regex")
    if message_regex and not re.search(str(message_regex), finding.message):
        return False

    source_needles = rule.get("source_contains_any") or []
    if source_needles:
        source = _source_for(finding.path)
        if not any(str(needle) in source for needle in source_needles):
            return False

    return True


def _run_vulture(args: list[str]) -> list[Finding]:
    cmd = [sys.executable, "-m", "vulture", *args]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    findings = [parsed for line in output.splitlines() if (parsed := Finding.parse(line))]
    if proc.returncode not in (0, 3):
        print(output, file=sys.stderr)
        raise SystemExit(proc.returncode)
    return findings


def _classify(findings: list[Finding], rules: list[dict[str, Any]]) -> Classification:
    by_rule: dict[str, list[Finding]] = {str(rule["id"]): [] for rule in rules}
    unclassified: list[Finding] = []
    never_allowlist: list[Finding] = []

    for finding in findings:
        if "unreachable code" in finding.message:
            never_allowlist.append(finding)
            continue
        matched = next((rule for rule in rules if _matches_rule(finding, rule)), None)
        if matched is None:
            unclassified.append(finding)
            continue
        by_rule[str(matched["id"])].append(finding)

    return Classification(by_rule, unclassified, never_allowlist)


def _counter_delta(current: list[str], expected: list[str]) -> tuple[list[str], list[str]]:
    current_counts = Counter(current)
    expected_counts = Counter(expected)
    added = sorted((current_counts - expected_counts).elements())
    removed = sorted((expected_counts - current_counts).elements())
    return added, removed


def _snapshot_deltas(
    rules: list[dict[str, Any]],
    classification: Classification,
) -> tuple[list[tuple[str, list[str]]], list[SnapshotDelta]]:
    missing: list[tuple[str, list[str]]] = []
    deltas: list[SnapshotDelta] = []
    for rule in rules:
        rule_id = str(rule["id"])
        current = sorted(finding.stable_key for finding in classification.by_rule[rule_id])
        expected = rule.get("findings")
        if not isinstance(expected, list):
            missing.append((rule_id, current))
            continue
        added, removed = _counter_delta(current, [str(item) for item in expected])
        delta = SnapshotDelta(rule_id, added, removed)
        if delta.changed:
            deltas.append(delta)
    return missing, deltas


def _print_summary(findings: list[Finding], classification: Classification) -> None:
    print("vulture baseline summary:")
    print(f"  total findings: {len(findings)}")
    for rule_id, accepted in sorted(classification.by_rule.items()):
        print(f"  {rule_id}: {len(accepted)}")
    print(f"  unclassified: {len(classification.unclassified)}")
    print(f"  never_allowlist: {len(classification.never_allowlist)}")


def _print_findings(title: str, findings: list[Finding]) -> None:
    if not findings:
        return
    print(f"\n{title}", file=sys.stderr)
    for finding in findings[:50]:
        print(f"  {finding.render()}", file=sys.stderr)


def _print_missing_snapshots(missing: list[tuple[str, list[str]]]) -> None:
    if not missing:
        return
    print("\nRules missing exact `findings` snapshots:", file=sys.stderr)
    for rule_id, current in missing:
        rendered = json.dumps(current, indent=2)
        print(f"\n  {rule_id} observed findings = {rendered}", file=sys.stderr)


def _print_snapshot_deltas(deltas: list[SnapshotDelta]) -> None:
    if not deltas:
        return
    print("\nReviewed finding snapshots changed:", file=sys.stderr)
    for delta in deltas:
        print(f"\n  {delta.rule_id}", file=sys.stderr)
        for key in delta.added[:50]:
            print(f"    + {key}", file=sys.stderr)
        for key in delta.removed[:50]:
            print(f"    - {key}", file=sys.stderr)


def main(argv: list[str]) -> int:
    scan_args = argv or ["packages", "tests", "--exclude", "*/.venv/*"]
    rules = _load_baseline()["rules"]
    findings = _run_vulture(scan_args)
    classification = _classify(findings, rules)
    missing, deltas = _snapshot_deltas(rules, classification)

    _print_summary(findings, classification)
    _print_findings(
        "Unreachable-code findings must be fixed:",
        classification.never_allowlist,
    )
    _print_findings(
        "Unclassified vulture findings need owner/category/rationale:",
        classification.unclassified,
    )
    _print_missing_snapshots(missing)
    _print_snapshot_deltas(deltas)

    failed = bool(
        classification.never_allowlist or classification.unclassified or missing or deltas
    )
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
