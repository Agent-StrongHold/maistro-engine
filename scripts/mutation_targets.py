#!/usr/bin/env python3
"""Map changed source files to the tests that should kill their mutants.

Mutation testing asks a narrow question — *do this file's tests catch changes
to this file?* — so both halves must be scoped to the file. The PR job used to
scope neither: `module-path` was the whole 126k-line package and the test
command ran all 5600+ core tests per mutant, which is why it hit the 30-minute
wall and reported "cancelled" on every PR that triggered it.

Resolution order for a source file's tests:

1. the mirror path — ``src/maistro/router/scorer.py`` → ``tests/router/test_scorer.py``
2. the nearest ancestor test directory — ``tests/router/``, then ``tests/``

Emits one ``<src>\\t<test-path>`` line per resolvable file. Files whose tests
resolve only to the whole suite are reported on stderr and SKIPPED rather than
silently mutated against everything: a per-file budget that quietly widens to
the full suite is how the 30-minute timeout happened in the first place.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE_SRC = Path("packages/maistro-core/src/maistro")
CORE_TESTS = Path("packages/maistro-core/tests")


def resolve_tests(src: str) -> Path | None:
    """Return the most specific existing test path for ``src``, or None."""
    path = Path(src)
    try:
        rel = path.relative_to(CORE_SRC)
    except ValueError:
        return None

    # The source must still exist. Everything below checks that a *test* path
    # exists and never that the file under test does, so a module deleted by
    # the PR — whose test directory naturally survives — used to resolve
    # happily, consume one of the capped slots ahead of a live modified file,
    # and then hand cosmic-ray a `module-path` pointing at nothing. The
    # workflow also filters deletions out of the diff; this is the half that
    # can be tested, and the half that holds if the diff is ever built
    # differently.
    if not (REPO / path).is_file():
        return None

    mirror = CORE_TESTS / rel.parent / f"test_{rel.stem}.py"
    if (REPO / mirror).is_file():
        return mirror

    # Walk up: tests/router/, tests/security/warden/ ... but never bare tests/,
    # which is the whole suite and defeats the point of scoping.
    parent = rel.parent
    while parent != Path("."):
        candidate = CORE_TESTS / parent
        if (REPO / candidate).is_dir():
            return candidate
        parent = parent.parent
    return None


# Mutation budget is finite, so when it has to be spent partially it is spent
# where a surviving mutant is worst. security/ and router/ first: an unkilled
# mutant in the Warden or the scorer is a silently-weakened control, where one
# in a graph node is usually a missing assertion.
_PRIORITY = (
    "src/maistro/security/",
    "src/maistro/policy/",
    "src/maistro/router/",
    "src/maistro/graph/",
)


def priority(src: str) -> int:
    for rank, prefix in enumerate(_PRIORITY):
        if prefix in src:
            return rank
    return len(_PRIORITY)


def main(argv: list[str]) -> int:
    limit = 0
    args = list(argv)
    if args and args[0] == "--limit":
        limit = int(args[1])
        args = args[2:]

    files = [line.strip() for line in (args[0].splitlines() if args else sys.stdin)]
    targets: list[tuple[str, Path]] = []
    for src in files:
        if not src:
            continue
        tests = resolve_tests(src)
        if tests is None:
            print(f"skip (no scoped tests found): {src}", file=sys.stderr)
            continue
        targets.append((src, tests))

    targets.sort(key=lambda t: (priority(t[0]), t[0]))

    if limit and len(targets) > limit:
        dropped = targets[limit:]
        targets = targets[:limit]
        # Never a silent truncation: a gate that quietly covers less than it
        # claims is the exact failure this whole workflow was rewritten to
        # remove. Name every file that did not get mutated.
        print(
            f"::warning::mutation budget limit={limit}; "
            f"{len(dropped)} changed file(s) NOT mutated in this run "
            "(full sweep runs on the develop -> main gate and nightly):",
            file=sys.stderr,
        )
        for src, _ in dropped:
            print(f"  not mutated: {src}", file=sys.stderr)

    for src, tests in targets:
        print(f"{src}\t{tests}")
    if not targets:
        print("no changed file resolved to a scoped test path", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
