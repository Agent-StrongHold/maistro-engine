"""The mutation job's file→tests mapping, tested rather than trusted.

This logic used to not exist: the PR mutation job mutated the whole package
against the whole test suite, hit its 30-minute wall, and reported "cancelled"
on every PR that triggered it. Scoping is what makes the gate finishable, so
the scoping itself needs to be correct — and the one outcome that must never
happen silently is "fell back to the entire suite", which is the behavior that
caused the timeout.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import ClassVar

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "mutation_targets.py"


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("_mutation_targets", SCRIPT)
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


def test_exact_mirror_is_preferred(module):
    got = module.resolve_tests("packages/maistro-core/src/maistro/router/scorer.py")
    assert got == Path("packages/maistro-core/tests/router/test_scorer.py")


def test_nested_mirror_resolves(module):
    got = module.resolve_tests("packages/maistro-core/src/maistro/security/warden/detector.py")
    assert got == Path("packages/maistro-core/tests/security/warden/test_detector.py")


def test_falls_back_to_nearest_test_directory(module):
    """No mirror file exists for harness_executor.py; the package's test dir is
    the most specific thing that does."""
    got = module.resolve_tests("packages/maistro-core/src/maistro/graph/harness_executor.py")
    assert got == Path("packages/maistro-core/tests/graph")


def test_never_falls_back_to_the_whole_suite(module):
    """The critical property. Returning bare `tests/` would restore exactly the
    unscoped run that made this job time out — so an unresolvable file must be
    skipped (None), never widened to everything."""
    got = module.resolve_tests("packages/maistro-core/src/maistro/nonexistent_subsystem/mod.py")
    assert got != Path("packages/maistro-core/tests")
    assert got is None


def test_files_outside_core_are_not_mapped(module):
    assert module.resolve_tests("packages/maistro-rsi/src/maistro_rsi/runner.py") is None
    assert module.resolve_tests("README.md") is None


def test_every_resolved_path_exists_on_disk(module):
    """A mapping that points at a path pytest can't collect would make every
    mutant 'killed' by usage error — the same vacuous-pass failure mode as the
    missing pytest-timeout plugin."""
    for src in (
        "packages/maistro-core/src/maistro/router/scorer.py",
        "packages/maistro-core/src/maistro/security/warden/detector.py",
        "packages/maistro-core/src/maistro/graph/harness_executor.py",
    ):
        resolved = module.resolve_tests(src)
        assert resolved is not None
        assert (REPO / resolved).exists(), resolved


class TestBudgetPrioritisation:
    """When the budget is partial, it is spent where a survivor is worst — and
    what got dropped is always named.

    The tiering: feature -> develop caps the file count for fast feedback,
    develop -> main runs a full sweep as the release gate.
    """

    ALL: ClassVar[list[str]] = [
        "packages/maistro-core/src/maistro/graph/harness_executor.py",
        "packages/maistro-core/src/maistro/router/scorer.py",
        "packages/maistro-core/src/maistro/security/warden/detector.py",
        "packages/maistro-core/src/maistro/memory/outcomes.py",
    ]

    def test_security_outranks_router_outranks_graph(self, module):
        ranks = [module.priority(p) for p in self.ALL]
        graph, router, security, other = ranks
        assert security < router < graph < other

    def test_limit_keeps_the_highest_priority_files(self, module, capsys):
        module.main(["--limit", "2", "\n".join(self.ALL)])
        out = capsys.readouterr()
        kept = [line.split("\t")[0] for line in out.out.strip().splitlines()]
        assert "security/warden/detector.py" in kept[0]
        assert "router/scorer.py" in kept[1]
        assert len(kept) == 2

    def test_dropped_files_are_named_not_silently_skipped(self, module, capsys):
        """The load-bearing property. A gate that quietly covers less than it
        claims is exactly the phantom-gate failure this workflow was rewritten
        to remove, so truncation must be loud and itemised."""
        module.main(["--limit", "1", "\n".join(self.ALL)])
        err = capsys.readouterr().err
        assert "::warning::" in err
        assert "NOT mutated" in err
        for dropped in ("router/scorer.py", "graph/harness_executor.py"):
            assert dropped in err, dropped

    def test_zero_limit_means_full_sweep(self, module, capsys):
        """The develop -> main release gate passes --limit 0."""
        module.main(["--limit", "0", "\n".join(self.ALL)])
        out = capsys.readouterr()
        assert len(out.out.strip().splitlines()) == len(self.ALL)
        assert "NOT mutated" not in out.err
