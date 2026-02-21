"""Tests for startup validation — CRIT-02."""

from __future__ import annotations

import pytest

from maistro.config.settings import Settings
from maistro.main import _validate_startup


class TestStartupValidation:
    """CRIT-02: App must refuse to start without API keys when require_auth=True."""

    def test_no_keys_require_auth_raises(self) -> None:
        settings = Settings(api_keys=[], require_auth=True)
        with pytest.raises(RuntimeError, match="No API keys configured"):
            _validate_startup(settings)

    def test_keys_present_passes(self) -> None:
        settings = Settings(api_keys=["test-key"], require_auth=True)
        _validate_startup(settings)  # Should not raise

    def test_require_auth_false_allows_no_keys(self) -> None:
        settings = Settings(api_keys=[], require_auth=False)
        _validate_startup(settings)  # Should not raise
