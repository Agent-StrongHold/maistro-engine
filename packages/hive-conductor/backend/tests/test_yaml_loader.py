"""Tests for the YAML department loader and RubricScorer adapter (ADR-060)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.departments import RubricEval
from eval.loader import all_departments, load_department
from eval.scorer import RubricScorer

YAML_DIR = Path(__file__).resolve().parents[2] / "eval" / "departments" / "yaml"

# ---------------------------------------------------------------------------
# Loader basics
# ---------------------------------------------------------------------------

ALL_DEPT_NAMES = [
    "creative_writing",
    "deep_research",
    "engineering",
    "finance",
    "hr_people_ops",
    "legal",
    "marketing",
    "press_releases",
    "product_management",
]


@pytest.mark.parametrize("dept", ALL_DEPT_NAMES)
def test_load_department_returns_rubric_evals(dept):
    evals = load_department(YAML_DIR / f"{dept}.yaml")
    assert len(evals) == 5, f"{dept} should have 5 evals"
    for e in evals:
        assert isinstance(e, RubricEval)
        assert e.department == dept
        assert e.eval_name
        assert len(e.criteria) >= 3


@pytest.mark.parametrize("dept", ALL_DEPT_NAMES)
def test_all_criteria_have_required_keys(dept):
    evals = load_department(YAML_DIR / f"{dept}.yaml")
    for ev in evals:
        for c in ev.criteria:
            assert "name" in c
            assert "weight" in c
            assert callable(c["check"])


def test_all_departments_registry():
    depts = all_departments()
    for name in ALL_DEPT_NAMES:
        assert name in depts, f"Missing department: {name}"
        assert len(depts[name]) == 5


def test_load_is_repeatable():
    """Loading the same file twice gives independent instances with same shape."""
    a = load_department(YAML_DIR / "marketing.yaml")
    b = load_department(YAML_DIR / "marketing.yaml")
    assert len(a) == len(b)
    for ea, eb in zip(a, b, strict=True):
        assert ea.eval_name == eb.eval_name
        assert len(ea.criteria) == len(eb.criteria)


# ---------------------------------------------------------------------------
# Functional scoring via the loader
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_product_management_scores_good_requirements():
    evals = load_department(YAML_DIR / "product_management.yaml")
    req_eval = next(e for e in evals if e.eval_name == "requirements_completeness")
    good = (
        "As a product manager, I want a dashboard so I can track performance. "
        "Acceptance criteria: given the user logs in, when they navigate to /dashboard, "
        "then they see real-time metrics. Non-functional: response < 200ms, security: "
        "OAuth2. Constraint: out of scope for v1: mobile. Measurable: 99% uptime."
    )
    result = await req_eval.score(good)
    assert result.score >= 60


@pytest.mark.asyncio
async def test_product_management_scores_poor_requirements():
    evals = load_department(YAML_DIR / "product_management.yaml")
    req_eval = next(e for e in evals if e.eval_name == "requirements_completeness")
    poor = "We need a better dashboard. It should look nice and be fast."
    result = await req_eval.score(poor)
    assert result.score < 60


@pytest.mark.asyncio
async def test_creative_writing_age_appropriate():
    evals = load_department(YAML_DIR / "creative_writing.yaml")
    age_eval = next(e for e in evals if e.eval_name == "age_appropriateness")
    good = "The happy bunny made a kind friend who was brave and fun to play with."
    result = await age_eval.score(good)
    assert result.score >= 50


@pytest.mark.asyncio
async def test_creative_writing_inappropriate_fails():
    evals = load_department(YAML_DIR / "creative_writing.yaml")
    age_eval = next(e for e in evals if e.eval_name == "age_appropriateness")
    bad = "The hero killed the dragon with blood everywhere. It was violent."
    result = await age_eval.score(bad)
    # no_inappropriate should fail (kill, blood, violence)
    flagged = next(d for d in result.details["criteria"] if d["name"] == "no_inappropriate")
    assert not flagged["passed"]


@pytest.mark.asyncio
async def test_deep_research_source_attribution():
    evals = load_department(YAML_DIR / "deep_research.yaml")
    src_eval = next(e for e in evals if e.eval_name == "source_attribution")
    good = "According to [1] Smith et al., the data shows [2] a 30% rise. Source: WHO [3]."
    result = await src_eval.score(good)
    assert result.score >= 60


@pytest.mark.asyncio
async def test_legal_plain_language_active_voice():
    evals = load_department(YAML_DIR / "legal.yaml")
    pl_eval = next(e for e in evals if e.eval_name == "plain_language")
    active = (
        "The parties will perform their obligations by Monday. "
        "The contractor will deliver the report. The client will pay within 30 days."
    )
    result = await pl_eval.score(active)
    av = next(d for d in result.details["criteria"] if d["name"] == "active_voice")
    assert av["passed"]


@pytest.mark.asyncio
async def test_legal_plain_language_passive_fails():
    evals = load_department(YAML_DIR / "legal.yaml")
    pl_eval = next(e for e in evals if e.eval_name == "plain_language")
    passive = (
        "The obligations shall be performed. The report shall be delivered. Payment shall be made."
    )
    result = await pl_eval.score(passive)
    av = next(d for d in result.details["criteria"] if d["name"] == "active_voice")
    assert not av["passed"]


@pytest.mark.asyncio
async def test_press_releases_ap_style_no_exclamation():
    evals = load_department(YAML_DIR / "press_releases.yaml")
    ap_eval = next(e for e in evals if e.eval_name == "ap_style")
    no_exclaim = "SEATTLE, June 1 — Acme Corp announced today that the new product is ready."
    result = await ap_eval.score(no_exclaim)
    exclaim_crit = next(
        d for d in result.details["criteria"] if d["name"] == "no_exclamation_marks"
    )
    assert exclaim_crit["passed"]


@pytest.mark.asyncio
async def test_hr_no_pii():
    evals = load_department(YAML_DIR / "hr_people_ops.yaml")
    conf_eval = next(e for e in evals if e.eval_name == "confidentiality")
    with_ssn = "Employee SSN: 123-45-6789. Please keep this confidential and secure."
    result = await conf_eval.score(with_ssn)
    pii_crit = next(d for d in result.details["criteria"] if d["name"] == "no_pii_exposed")
    assert not pii_crit["passed"]


# ---------------------------------------------------------------------------
# RubricScorer adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rubric_scorer_value_range():
    evals = load_department(YAML_DIR / "marketing.yaml")
    scorer = RubricScorer(evals[0])
    score = await scorer.score("innovative trusted solution for your team today!")
    assert 0.0 <= score.value <= 1.0
    assert score.provider == "rubric"
    assert score.rationale


@pytest.mark.asyncio
async def test_rubric_scorer_passed_threshold():
    evals = load_department(YAML_DIR / "engineering.yaml")
    scorer = RubricScorer(evals[0])  # tests_pass eval
    good = (
        "def test_create_user():\n"
        "    result = create_user('alice')\n"
        "    assert result.success\n\n"
        "def test_create_user_empty():\n"
        "    result = create_user('')\n"
        "    assert result.error == 'empty'\n\n"
        "def test_create_user_invalid_raises():\n"
        "    with pytest.raises(ValueError):\n"
        "        create_user(None)\n"
    )
    score = await scorer.score(good)
    assert score.passed  # ≥50% score
    assert len(score.evidence) > 0  # some criteria passed


@pytest.mark.asyncio
async def test_rubric_scorer_from_yaml():
    scorer = RubricScorer.from_yaml(YAML_DIR / "finance.yaml", eval_index=0)
    score = await scorer.score(
        "Total revenue: $1.2M (12.5% growth). GAAP net income: $340K. "
        "Disclaimer: not financial advice. Source: Q2 2026 financial statements."
    )
    assert score.value > 0
