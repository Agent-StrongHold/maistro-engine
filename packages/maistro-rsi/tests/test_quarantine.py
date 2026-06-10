"""Tests tied to SPEC.md §2 (quarantine gate) acceptance criteria quarantine-1..5."""

from __future__ import annotations

import pytest

from maistro.security._types import WardenVerdict
from maistro_rsi.quarantine import quarantine_scan


class FakeWarden:
    def __init__(self, verdict: WardenVerdict) -> None:
        self._verdict = verdict
        self.scan_calls: list[tuple[str, str]] = []

    async def scan(self, content, boundary="default"):
        self.scan_calls.append((content, boundary))
        return self._verdict


class FakeAdversarialReview:
    def __init__(self, *, approve: bool) -> None:
        self.approve = approve
        self.review_calls: list[tuple[str, list[str]]] = []

    async def review(self, diff, touched_paths):
        self.review_calls.append((diff, touched_paths))
        return self.approve


ORDINARY_PATHS = ["packages/maistro-core/src/maistro/agents/base.py"]
SENSITIVE_PATHS = ["packages/maistro-rsi/src/maistro_rsi/quarantine.py", "README.md"]


class TestQuarantineScan:
    @pytest.mark.asyncio
    async def test_flagged_diff_never_clears_regardless_of_touched_paths(self):
        """quarantine-1: cleared is False whenever the Warden verdict is not clean."""
        flagged = WardenVerdict(clean=False, flags=("secret_leak",))

        ordinary = await quarantine_scan("diff", ORDINARY_PATHS, FakeWarden(flagged))
        sensitive = await quarantine_scan("diff", SENSITIVE_PATHS, FakeWarden(flagged))

        assert ordinary.cleared is False
        assert sensitive.cleared is False

    @pytest.mark.asyncio
    async def test_clean_diff_touching_no_sensitive_surface_clears_without_review(self):
        """quarantine-2: a clean diff touching ordinary surface clears, no adversarial review required."""
        clean = WardenVerdict(clean=True, flags=())

        verdict = await quarantine_scan("diff", ORDINARY_PATHS, FakeWarden(clean))

        assert verdict.cleared is True
        assert verdict.requires_adversarial_review is False

    @pytest.mark.asyncio
    async def test_diff_touching_any_sensitive_path_requires_adversarial_review(self):
        """quarantine-3: touching even one sensitive-surface path sets requires_adversarial_review,
        regardless of the Warden verdict."""
        clean = WardenVerdict(clean=True, flags=())
        flagged = WardenVerdict(clean=False, flags=("secret_leak",))

        clean_verdict = await quarantine_scan("diff", SENSITIVE_PATHS, FakeWarden(clean))
        flagged_verdict = await quarantine_scan("diff", SENSITIVE_PATHS, FakeWarden(flagged))

        assert clean_verdict.requires_adversarial_review is True
        assert flagged_verdict.requires_adversarial_review is True

    @pytest.mark.asyncio
    async def test_cleared_requires_clean_warden_and_no_pending_adversarial_review(self):
        """quarantine-4: cleared is True only when Warden is clean AND (no review required OR
        a supplied adversarial review passed). A pending/missing review on a sensitive diff
        must never clear."""
        clean = WardenVerdict(clean=True, flags=())

        # Sensitive-surface diff, no adversarial reviewer supplied -> pending, never clears.
        pending = await quarantine_scan("diff", SENSITIVE_PATHS, FakeWarden(clean))
        assert pending.cleared is False
        assert pending.requires_adversarial_review is True

        # Sensitive-surface diff, reviewer supplied and approves -> clears.
        approved = await quarantine_scan(
            "diff", SENSITIVE_PATHS, FakeWarden(clean), adversarial_review=FakeAdversarialReview(approve=True),
        )
        assert approved.cleared is True

        # Sensitive-surface diff, reviewer supplied and rejects -> never clears.
        rejected = await quarantine_scan(
            "diff", SENSITIVE_PATHS, FakeWarden(clean), adversarial_review=FakeAdversarialReview(approve=False),
        )
        assert rejected.cleared is False

    @pytest.mark.asyncio
    async def test_flags_surface_warden_flags_verbatim(self):
        """quarantine-5: the verdict's flags carry the Warden flags verbatim, unsummarized."""
        flagged = WardenVerdict(clean=False, flags=("secret_leak", "prompt_injection"))

        verdict = await quarantine_scan("diff", ORDINARY_PATHS, FakeWarden(flagged))

        assert verdict.flags == ("secret_leak", "prompt_injection")
