"""Tests for constant-time secret comparison.

Evidence source: OpenClaw's secret-equal.ts uses HMAC-SHA256 before
timingSafeEqual to prevent timing attacks via length leakage.
"""

from __future__ import annotations

from maistro.security.secret_equal import secret_equal


class TestSecretEqual:
    """Evidence: OpenClaw's implementation hashes both inputs with HMAC-SHA256
    before comparison, producing fixed-length 32-byte digests regardless of
    input length. This prevents timing attacks that could leak length info."""

    def test_equal_strings(self) -> None:
        assert secret_equal("abc123", "abc123") is True

    def test_unequal_strings(self) -> None:
        assert secret_equal("abc123", "abc124") is False

    def test_different_lengths(self) -> None:
        """Evidence: Different-length strings should be handled safely
        without leaking length information through timing."""
        assert secret_equal("short", "a-much-longer-string") is False

    def test_empty_strings(self) -> None:
        assert secret_equal("", "") is True

    def test_empty_vs_nonempty(self) -> None:
        assert secret_equal("", "notempty") is False

    def test_unicode_strings(self) -> None:
        assert secret_equal("héllo", "héllo") is True
        assert secret_equal("héllo", "hello") is False

    def test_type_confusion_int(self) -> None:
        """Evidence: OpenClaw defends against type confusion by performing
        a dummy comparison for non-string inputs."""
        assert secret_equal(123, "123") is False  # type: ignore[arg-type]

    def test_type_confusion_none(self) -> None:
        assert secret_equal(None, "test") is False  # type: ignore[arg-type]

    def test_type_confusion_both_nonstring(self) -> None:
        assert secret_equal(123, 456) is False  # type: ignore[arg-type]

    def test_long_tokens(self) -> None:
        """Evidence: Real API tokens are typically 40-100+ characters."""
        token = "sk-ant-api03-" + "a" * 80
        assert secret_equal(token, token) is True
        assert secret_equal(token, token[:-1] + "b") is False
