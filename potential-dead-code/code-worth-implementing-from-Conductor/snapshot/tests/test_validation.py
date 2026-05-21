"""Tests for gateway validation utilities."""

from __future__ import annotations

import pytest

from gateway.validation import (
    ValidationError,
    validate_project_id,
    validate_task_id,
    sanitize_for_log,
)


class TestProjectIdValidation:
    """Project ID validation tests."""

    @pytest.mark.parametrize(
        "valid_id",
        [
            "myproject",
            "my-project",
            "my_project",
            "Project123",
            "a",
            "a" * 64,  # Max length
        ],
    )
    def test_accepts_valid_ids(self, valid_id: str):
        """Should accept various valid project IDs."""
        assert validate_project_id(valid_id) == valid_id

    @pytest.mark.parametrize(
        "invalid_id,match",
        [
            ("", "cannot be empty"),
            ("../etc", "Invalid project ID"),
            ("my/project", "Invalid project ID"),
            ("my\\project", "Invalid project ID"),
            ("-myproject", "Invalid project ID"),
            ("_myproject", "Invalid project ID"),
            ("a" * 65, "Invalid project ID"),  # Too long
            ("project@name", "Invalid project ID"),
        ],
    )
    def test_rejects_invalid_ids(self, invalid_id: str, match: str):
        """Should reject various invalid project IDs."""
        with pytest.raises(ValidationError, match=match):
            validate_project_id(invalid_id)


class TestTaskIdValidation:
    """Task ID validation tests."""

    @pytest.mark.parametrize(
        "valid_id",
        [
            "task-123",
            "task_abc",
            "T",
            "a" * 128,  # Max length
        ],
    )
    def test_accepts_valid_ids(self, valid_id: str):
        """Should accept various valid task IDs."""
        assert validate_task_id(valid_id) == valid_id

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "",
            "-task",
            "task@#$%",
            "a" * 129,  # Too long
        ],
    )
    def test_rejects_invalid_ids(self, invalid_id: str):
        """Should reject various invalid task IDs."""
        with pytest.raises(ValidationError):
            validate_task_id(invalid_id)


class TestSanitizeForLog:
    """Log sanitization tests."""

    def test_truncates_long_text(self):
        """Long text should be truncated."""
        long_text = "a" * 300
        result = sanitize_for_log(long_text, max_length=100)
        assert len(result) == 100
        assert result.endswith("...")

    @pytest.mark.parametrize(
        "input_text,expected_clean",
        [
            ("line1\nline2", "line1 line2"),
            ("tab\there", "tab here"),
            ("null\x00char", "null char"),
            ("\x1b[31mred\x1b[0m", " [31mred [0m"),  # ANSI codes
        ],
    )
    def test_replaces_control_chars(self, input_text: str, expected_clean: str):
        """Control characters should be replaced."""
        result = sanitize_for_log(input_text)
        assert result == expected_clean

    def test_short_text_unchanged(self):
        """Short clean text should be unchanged."""
        text = "hello world"
        assert sanitize_for_log(text) == "hello world"

    def test_empty_string(self):
        """Empty string should return empty."""
        assert sanitize_for_log("") == ""

    def test_custom_max_length(self):
        """Should respect custom max_length."""
        text = "a" * 50
        result = sanitize_for_log(text, max_length=20)
        assert len(result) == 20
