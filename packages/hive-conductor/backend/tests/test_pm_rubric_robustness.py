"""The PM RequirementsCompleteness rubric must reward artifact STRUCTURE, not keywords.

Guards against a hill-climber satisfying the rubric by stuffing the right words.
"""

from __future__ import annotations

import asyncio

from eval.departments.product_management import RequirementsCompleteness


def _score(text: str) -> int:
    return asyncio.run(RequirementsCompleteness().score(text)).score


def test_keyword_stuffing_scores_low() -> None:
    """Right words, wrong structure: 'as a' and 'i want' far apart, given/when w/o then."""
    stuffed = (
        "Notes: as a. " + ("filler " * 30) + " i want. "
        "given the inputs when ready. discusses performance and security."
    )
    # Only has_non_functional (performance/security) should pass → ~20/100.
    assert _score(stuffed) < 50


def test_real_requirements_score_high() -> None:
    real = """
    As a registered user, I want to reset my password so that I can regain access.

    Acceptance criteria:
      Given a valid email, When I request a reset, Then I receive a link within 60 seconds.

    Non-functional: performance under 200 ms, security via argon2id.
    Constraints: out of scope — enterprise SSO.
    The reset link expires after 15 minutes; 99% of resets complete in under 5 seconds.
    """
    assert _score(real) >= 80
