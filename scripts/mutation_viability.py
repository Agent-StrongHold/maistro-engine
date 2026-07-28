"""Classify surviving cosmic-ray mutants by whether any test could kill them.

The mutation gate scores `killed / total`. That is only a meaningful ratio if
every mutant in the denominator is *killable*. Some are not: a mutation applied
inside a type annotation cannot change runtime behaviour in a module that
carries `from __future__ import annotations`, because annotations are never
evaluated there. cosmic-ray cannot mark those `INCOMPETENT` -- that status is
for mutants which fail to compile, and these compile fine -- so they land in the
survivor list and drag the ratio down permanently.

`graph/durable_runs/executor.py` is the worked example: 139 survivors, of which
69 are annotation-only. Killing every genuinely killable mutant in that file
still tops out below the 90% gate. The ceiling is a property of the denominator,
not of the test suite.

This module answers three questions, in order:

  locate   -- which surviving mutants are candidates? (join the session DB)
  confirm  -- is a candidate *provably* non-viable? (compare stripped ASTs)
  mark     -- emit a machine-readable report the gate can subtract, naming
              every exclusion so nothing is dropped silently.

The confirmation step is a proof rather than a heuristic. For each survivor we
reconstruct the mutated source, strip every annotation from both the pristine
and the mutated AST, and compare. If the two are identical, the mutation lives
entirely in annotation space: no expression the interpreter evaluates differs,
so no test can observe it. If they differ at all -- including a mutation that
turns a keyword-only marker `*,` into a positional-only `/,`, which really does
change the call contract -- the mutant is viable and stays in the denominator.

Deliberately *not* excluded:

  - anything whose stripped AST differs, however marginally
  - mutants that fail to compile (reported separately as `invalid`; these are a
    cosmic-ray classification bug, not a coverage gap, but they are not silently
    folded into the viable count either)

Usage:
    python scripts/mutation_viability.py SESSION.sqlite [--json report.json]
"""

from __future__ import annotations

import argparse
import ast
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class _StripAnnotations(ast.NodeTransformer):
    """Remove every annotation, leaving the executable structure intact.

    Annotations are the only construct we are willing to call unobservable, so
    they are the only thing removed. Everything else -- defaults, decorators,
    the argument vector's shape, posonly/kwonly placement -- is preserved
    precisely so that a mutation touching any of it shows up as a difference.
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node.returns = None
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        node.returns = None
        return self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.annotation = None
        return self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        # `x: T = v` -> `x = v`; a bare `x: T` declares nothing at runtime.
        self.generic_visit(node)
        if node.value is None:
            return ast.Pass()
        return ast.Assign(targets=[node.target], value=node.value, type_comment=None)


def _normalized(source: str) -> str | None:
    """AST dump with annotations stripped, or None if the source won't parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    stripped = ast.fix_missing_locations(_StripAnnotations().visit(tree))
    # include_attributes=False: line/column shifts are not behavioural.
    return ast.dump(stripped, include_attributes=False)


def _apply_diff(pristine: str, diff: str) -> str | None:
    """Rebuild the mutated source from a cosmic-ray single-hunk diff.

    cosmic-ray mutates exactly one node, so each diff carries one `-`/`+` pair.
    We locate it by hunk header rather than by searching for the text, because
    the same line can occur more than once in a file.
    """
    lines = pristine.splitlines(keepends=True)
    start: int | None = None
    removed: list[str] = []
    added: list[str] = []
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            # "@@ -330,7 +330,7 @@" -> 330 (1-based)
            try:
                start = int(raw.split("-", 1)[1].split(",", 1)[0].split()[0])
            except (IndexError, ValueError):
                return None
            removed, added = [], []
        elif raw.startswith("---") or raw.startswith("+++"):
            continue
        elif raw.startswith("-"):
            removed.append(raw[1:])
        elif raw.startswith("+"):
            added.append(raw[1:])
    if start is None or len(removed) != 1 or len(added) != 1:
        return None

    target = removed[0]
    # Scan the hunk window for the removed line; hunk headers are 1-based and
    # include leading context, so the changed line is at or after `start`.
    for idx in range(max(0, start - 1), min(len(lines), start + 12)):
        if lines[idx].rstrip("\n") == target.rstrip("\n"):
            out = list(lines)
            newline = "\n" if lines[idx].endswith("\n") else ""
            out[idx] = added[0].rstrip("\n") + newline
            return "".join(out)
    return None


@dataclass
class Verdict:
    """One survivor's classification."""

    row: int
    operator: str
    category: str  # "non_viable" | "viable" | "invalid" | "undetermined"
    source_line: str
    mutated_line: str = ""


@dataclass
class Report:
    total: int = 0
    killed: int = 0
    survived: int = 0
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def non_viable(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.category == "non_viable"]

    @property
    def viable(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.category == "viable"]

    @property
    def invalid(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.category == "invalid"]

    @property
    def undetermined(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.category == "undetermined"]

    def adjusted(self) -> tuple[int, int, float]:
        """(killed, adjusted_total, rate) with non-viable mutants removed.

        `undetermined` mutants stay in the denominator. A mutant we could not
        reconstruct is not thereby proven harmless, and the gate must not be
        loosened by a parsing failure in this script.
        """
        denominator = self.total - len(self.non_viable) - len(self.invalid)
        rate = self.killed / denominator if denominator else 0.0
        return self.killed, denominator, rate


def classify(session_path: Path, module_path: Path) -> Report:
    """Locate survivors in the session, then confirm each one's viability."""
    pristine = module_path.read_text()
    baseline = _normalized(pristine)
    if baseline is None:
        raise SystemExit(f"pristine source does not parse: {module_path}")
    src_lines = pristine.splitlines()

    conn = sqlite3.connect(session_path)
    report = Report()
    report.total = conn.execute("SELECT count(*) FROM work_results").fetchone()[0]
    report.killed = conn.execute(
        "SELECT count(*) FROM work_results WHERE test_outcome = 'KILLED'"
    ).fetchone()[0]

    rows = conn.execute(
        """SELECT s.start_pos_row, s.operator_name, r.diff
             FROM mutation_specs s JOIN work_results r ON s.job_id = r.job_id
            WHERE r.test_outcome = 'SURVIVED'
            ORDER BY s.start_pos_row"""
    ).fetchall()
    report.survived = len(rows)

    for row, operator, diff in rows:
        line_text = src_lines[row - 1].strip() if 0 < row <= len(src_lines) else ""
        mutated = _apply_diff(pristine, diff or "")
        if mutated is None:
            report.verdicts.append(Verdict(row, operator, "undetermined", line_text))
            continue
        candidate = _normalized(mutated)
        if candidate is None:
            report.verdicts.append(Verdict(row, operator, "invalid", line_text))
            continue
        category = "non_viable" if candidate == baseline else "viable"
        mutated_line = mutated.splitlines()[row - 1].strip() if row <= len(src_lines) else ""
        report.verdicts.append(Verdict(row, operator, category, line_text, mutated_line))

    conn.close()
    return report


def _emit(report: Report, module_path: Path, json_out: Path | None) -> None:
    killed, denominator, rate = report.adjusted()
    raw_rate = report.killed / report.total if report.total else 0.0

    print(f"module: {module_path}")
    print(f"  raw       : {report.killed}/{report.total} = {raw_rate:.1%}")
    print(f"  survivors : {report.survived}")
    print(f"    non-viable (annotation-only, provably unkillable) : {len(report.non_viable)}")
    print(f"    invalid    (does not compile)                     : {len(report.invalid)}")
    print(f"    undetermined (kept in denominator)                : {len(report.undetermined)}")
    print(f"    viable     (real coverage gaps)                   : {len(report.viable)}")
    print(f"  adjusted  : {killed}/{denominator} = {rate:.1%}")
    print()

    if report.non_viable:
        print("excluded as non-viable (every one named; nothing is dropped silently):")
        for op, n in Counter(v.operator for v in report.non_viable).most_common():
            print(f"  {n:4d}  {op}")
        print()

    if report.viable:
        print("viable survivors -- these are real coverage gaps, write tests for them:")
        for v in report.viable:
            print(f"  L{v.row:<5d} {v.operator}")
            print(f"          - {v.source_line[:78]}")
            print(f"          + {v.mutated_line[:78]}")

    if json_out:
        payload: dict[str, Any] = {
            "module": str(module_path),
            "raw": {"killed": report.killed, "total": report.total},
            "adjusted": {"killed": killed, "total": denominator, "rate": rate},
            "non_viable": [
                {"line": v.row, "operator": v.operator, "source": v.source_line}
                for v in report.non_viable
            ],
            "viable": [
                {"line": v.row, "operator": v.operator, "source": v.source_line}
                for v in report.viable
            ],
        }
        json_out.write_text(json.dumps(payload, indent=2))
        print(f"\nwrote {json_out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="cosmic-ray session sqlite")
    parser.add_argument("module", type=Path, help="the pristine mutated module")
    parser.add_argument("--json", type=Path, default=None, help="write a JSON report here")
    args = parser.parse_args(argv)

    report = classify(args.session, args.module)
    _emit(report, args.module, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
