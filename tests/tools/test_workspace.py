"""Tests for workspace path validation.

Evidence: Sandbox containers must only mount from allowed host prefixes
to prevent arbitrary filesystem access. This mirrors OpenClaw's
validate-sandbox-security.ts path validation.
"""

from __future__ import annotations

import pytest

from maistro.tools.sandbox.workspace import validate_workspace_path


class TestWorkspaceValidation:
    """Evidence: Only /tmp/maistro-workspace and /repos/ prefixes are
    allowed for container mounts."""

    def test_allowed_tmp_path(self) -> None:
        path = validate_workspace_path("/tmp/maistro-workspace/myrepo")
        assert str(path).startswith("/tmp/maistro-workspace")

    def test_allowed_repos_path(self) -> None:
        path = validate_workspace_path("/repos/my-org/my-repo")
        assert str(path).startswith("/repos")

    def test_blocked_etc(self) -> None:
        with pytest.raises(ValueError, match="not in an allowed location"):
            validate_workspace_path("/etc")

    def test_blocked_root(self) -> None:
        with pytest.raises(ValueError, match="not in an allowed location"):
            validate_workspace_path("/root/.ssh")

    def test_blocked_arbitrary(self) -> None:
        with pytest.raises(ValueError, match="not in an allowed location"):
            validate_workspace_path("/home/user/malicious")

    def test_blocked_var_run_docker(self) -> None:
        with pytest.raises(ValueError, match="not in an allowed location"):
            validate_workspace_path("/var/run/docker.sock")
