"""Tests for the TDD red->green gate (pure predicate; no real test runs)."""

from __future__ import annotations

from maistro_evolve.tdd_gate import TddEvidence, changed_test_paths, tdd_gate


def test_changed_test_paths_filters_tests() -> None:
    paths = [
        "src/foo.py",
        "packages/x/tests/test_foo.py",
        "src/bar_test.py",
        "conftest.py",
        "README.md",
    ]
    assert changed_test_paths(paths) == [
        "packages/x/tests/test_foo.py",
        "src/bar_test.py",
        "conftest.py",
    ]


def test_mode1_test_first_red_then_green_passes() -> None:
    ev = TddEvidence(changed_tests=["test_x.py"], baseline_changed_rc=1, candidate_changed_rc=0)
    g = tdd_gate(ev)
    assert g.passed is True
    assert "red on baseline" in g.reason


def test_vacuous_test_passing_on_baseline_fails() -> None:
    ev = TddEvidence(changed_tests=["test_x.py"], baseline_changed_rc=0, candidate_changed_rc=0)
    g = tdd_gate(ev)
    assert g.passed is False
    assert "vacuous" in g.reason


def test_changed_test_not_green_on_candidate_fails() -> None:
    ev = TddEvidence(changed_tests=["test_x.py"], baseline_changed_rc=1, candidate_changed_rc=1)
    assert tdd_gate(ev).passed is False


def test_mode2_fixing_failing_test_without_new_tests_passes() -> None:
    ev = TddEvidence(changed_tests=[], baseline_suite_failures=3, candidate_suite_failures=1)
    g = tdd_gate(ev)
    assert g.passed is True
    assert "fixed 2" in g.reason


def test_code_without_test_and_no_fix_fails() -> None:
    ev = TddEvidence(changed_tests=[], baseline_suite_failures=0, candidate_suite_failures=0)
    g = tdd_gate(ev)
    assert g.passed is False
    assert "not TDD" in g.reason
