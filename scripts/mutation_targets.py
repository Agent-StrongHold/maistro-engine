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


def main(argv: list[str]) -> int:
    files = [line.strip() for line in (argv[0].splitlines() if argv else sys.stdin)]
    resolved = 0
    for src in files:
        if not src:
            continue
        tests = resolve_tests(src)
        if tests is None:
            print(f"skip (no scoped tests found): {src}", file=sys.stderr)
            continue
        print(f"{src}\t{tests}")
        resolved += 1
    if resolved == 0:
        print("no changed file resolved to a scoped test path", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
