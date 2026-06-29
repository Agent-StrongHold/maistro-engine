#!/usr/bin/env python3
"""Run vulture and fail on unclassified or never-allowlisted findings.

This is a ratchet, not a blanket suppression: findings must match a reviewed
category rule in quality/vulture-baseline.json. High-confidence unreachable code
is always treated as a fix-now error because it has no legitimate dynamic-use
explanation.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
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

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message} ({self.confidence}% confidence)"


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


def main(argv: list[str]) -> int:
    scan_args = argv or ["packages", "tests", "--exclude", "*/.venv/*"]
    baseline = _load_baseline()
    rules = baseline["rules"]

    findings = _run_vulture(scan_args)
    classified: dict[str, int] = {}
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
        key = str(matched["id"])
        classified[key] = classified.get(key, 0) + 1

    print("vulture baseline summary:")
    print(f"  total findings: {len(findings)}")
    for rule_id, count in sorted(classified.items()):
        print(f"  {rule_id}: {count}")
    print(f"  unclassified: {len(unclassified)}")
    print(f"  never_allowlist: {len(never_allowlist)}")

    if never_allowlist:
        print("\nUnreachable-code findings must be fixed:", file=sys.stderr)
        for finding in never_allowlist[:50]:
            print(f"  {finding.render()}", file=sys.stderr)
    if unclassified:
        print("\nUnclassified vulture findings need owner/category/rationale:", file=sys.stderr)
        for finding in unclassified[:50]:
            print(f"  {finding.render()}", file=sys.stderr)

    return 1 if never_allowlist or unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
