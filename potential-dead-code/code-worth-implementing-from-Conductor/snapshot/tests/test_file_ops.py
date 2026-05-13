"""Tests for FileOps — security and functionality."""

from __future__ import annotations

import pytest
from pathlib import Path

from orchestrator.tools.file_ops import FileOps, MAX_FILE_SIZE_BYTES


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "project"
    project.mkdir()
    return project


@pytest.fixture
def file_ops(project_dir: Path) -> FileOps:
    return FileOps(project_dir)


class TestPathTraversal:
    """Security: Path traversal prevention."""

    @pytest.mark.parametrize(
        "malicious_path",
        [
            "../etc/passwd",
            "subdir/../../../etc/passwd",
            "..\\windows\\system32",
            "/etc/passwd",
            "/absolute/path/to/file",
        ],
    )
    def test_rejects_traversal_patterns(self, file_ops: FileOps, malicious_path: str):
        """Various traversal patterns should be rejected."""
        with pytest.raises(PermissionError, match="Forbidden path pattern"):
            file_ops.read(malicious_path)

    @pytest.mark.parametrize(
        "forbidden_component",
        [
            ".git/config",
            ".git/HEAD",
            ".env",
            "subdir/.env",
            "deep/nested/.git/objects",
        ],
    )
    def test_rejects_forbidden_components(self, file_ops: FileOps, forbidden_component: str):
        """Forbidden path components should be rejected."""
        with pytest.raises(PermissionError, match="Forbidden path component"):
            file_ops.read(forbidden_component)

    @pytest.mark.parametrize(
        "valid_path",
        [
            "file.txt",
            "subdir/file.txt",
            "deeply/nested/path/file.py",
            "git_readme.md",  # Contains 'git' but not '.git'
            "env_config.yaml",  # Contains 'env' but not '.env'
        ],
    )
    def test_accepts_valid_paths(self, file_ops: FileOps, valid_path: str):
        """Valid paths should not raise permission errors."""
        # This should raise FileNotFoundError, not PermissionError
        with pytest.raises(FileNotFoundError):
            file_ops.read(valid_path)


class TestFileSizeLimits:
    """Security: File size limits."""

    def test_rejects_oversized_write(self, file_ops: FileOps):
        """Writing content larger than MAX_FILE_SIZE_BYTES should fail."""
        huge_content = "x" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(ValueError, match="Content too large"):
            file_ops.write("huge.txt", huge_content)

    def test_accepts_content_at_limit(self, file_ops: FileOps):
        """Content well under limit should be accepted."""
        content = "x" * (MAX_FILE_SIZE_BYTES // 2)
        file_ops.write("ok.txt", content)
        assert file_ops.exists("ok.txt")

    def test_accepts_exactly_max_size(self, file_ops: FileOps):
        """Content exactly at limit should be accepted."""
        content = "x" * MAX_FILE_SIZE_BYTES
        file_ops.write("exact.txt", content)
        assert file_ops.exists("exact.txt")

    def test_rejects_reading_oversized_file(self, file_ops: FileOps, project_dir: Path):
        """Reading a file larger than MAX_FILE_SIZE_BYTES should fail."""
        large_file = project_dir / "large.bin"
        large_file.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 1))

        with pytest.raises(ValueError, match="File too large"):
            file_ops.read("large.bin")


class TestBasicOperations:
    """Functional tests for read/write/exists/list."""

    def test_write_and_read(self, file_ops: FileOps):
        """Basic write and read cycle."""
        file_ops.write("test.txt", "hello world")
        content = file_ops.read("test.txt")
        assert content == "hello world"

    def test_write_creates_subdirectories(self, file_ops: FileOps):
        """Write should create parent directories."""
        file_ops.write("a/b/c/deep.txt", "nested")
        assert file_ops.exists("a/b/c/deep.txt")
        assert file_ops.read("a/b/c/deep.txt") == "nested"

    def test_write_overwrites_existing(self, file_ops: FileOps):
        """Write should overwrite existing file."""
        file_ops.write("test.txt", "original")
        file_ops.write("test.txt", "updated")
        assert file_ops.read("test.txt") == "updated"

    def test_exists_returns_false_for_missing(self, file_ops: FileOps):
        """exists() should return False for nonexistent files."""
        assert not file_ops.exists("missing.txt")

    def test_exists_returns_true_for_existing(self, file_ops: FileOps):
        """exists() should return True for existing files."""
        file_ops.write("present.txt", "here")
        assert file_ops.exists("present.txt")

    def test_exists_returns_false_for_traversal(self, file_ops: FileOps):
        """exists() should return False (not raise) for traversal attempts."""
        assert not file_ops.exists("../outside")

    def test_read_missing_file_raises(self, file_ops: FileOps):
        """Reading missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            file_ops.read("nope.txt")

    def test_read_empty_file(self, file_ops: FileOps):
        """Reading empty file should return empty string."""
        file_ops.write("empty.txt", "")
        assert file_ops.read("empty.txt") == ""


class TestListDir:
    """Directory listing tests."""

    def test_list_dir_excludes_hidden(self, file_ops: FileOps, project_dir: Path):
        """list_dir should exclude hidden files."""
        (project_dir / "visible.txt").write_text("hi")
        (project_dir / ".hidden").write_text("secret")

        files = file_ops.list_dir(".")
        assert "visible.txt" in files
        assert ".hidden" not in files

    def test_list_dir_shows_subdirectories(self, file_ops: FileOps):
        """list_dir should show subdirectories."""
        file_ops.write("subdir/file.txt", "test")

        files = file_ops.list_dir(".")
        assert "subdir" in files

    def test_list_dir_nonexistent(self, file_ops: FileOps):
        """list_dir on nonexistent path should return empty or raise."""
        files = file_ops.list_dir("nonexistent")
        assert files == []

    def test_list_dir_in_subdirectory(self, file_ops: FileOps):
        """list_dir should work in subdirectories."""
        file_ops.write("sub/a.txt", "a")
        file_ops.write("sub/b.txt", "b")

        files = file_ops.list_dir("sub")
        # Returns relative paths from project root
        assert any("a.txt" in f for f in files)
        assert any("b.txt" in f for f in files)


class TestFileTypes:
    """File type handling tests."""

    def test_binary_like_content(self, file_ops: FileOps):
        """Should handle text that looks like binary."""
        content = "def x():\n    return b'\\x00\\x01'"
        file_ops.write("binary_like.py", content)
        assert file_ops.read("binary_like.py") == content

    def test_unicode_content(self, file_ops: FileOps):
        """Should handle unicode content."""
        content = "def greet(): return '你好世界 🌍'"
        file_ops.write("unicode.py", content)
        assert file_ops.read("unicode.py") == content

    def test_multiline_content(self, file_ops: FileOps):
        """Should preserve multiline content."""
        content = "line1\nline2\nline3\n"
        file_ops.write("multiline.txt", content)
        assert file_ops.read("multiline.txt") == content
