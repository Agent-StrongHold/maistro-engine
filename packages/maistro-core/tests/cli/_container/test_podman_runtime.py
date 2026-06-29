"""Tests for maistro.cli._container.podman_runtime — Podman socket discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maistro.cli._container.podman_runtime import PodmanRuntime


class TestFindSocket:
    def test_finds_xdg_runtime_dir_socket(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
        monkeypatch.setattr(
            "maistro.cli._container.podman_runtime.os.path.exists",
            lambda p: p == "/run/user/1000/podman/podman.sock",
        )
        result = PodmanRuntime._find_socket()
        assert result == "/run/user/1000/podman/podman.sock"

    def test_falls_back_to_rootful_socket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
        monkeypatch.setattr(
            "maistro.cli._container.podman_runtime.os.path.exists",
            lambda p: p == "/run/podman/podman.sock",
        )
        result = PodmanRuntime._find_socket()
        assert result == "/run/podman/podman.sock"

    def test_returns_none_when_no_socket_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
        monkeypatch.setattr("maistro.cli._container.podman_runtime.os.path.exists", lambda p: False)
        result = PodmanRuntime._find_socket()
        assert result is None

    def test_uses_uid_fallback_when_xdg_runtime_dir_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setattr("maistro.cli._container.podman_runtime.os.getuid", lambda: 1234)
        monkeypatch.setattr(
            "maistro.cli._container.podman_runtime.os.path.exists",
            lambda p: p == "/run/user/1234/podman/podman.sock",
        )
        result = PodmanRuntime._find_socket()
        assert result == "/run/user/1234/podman/podman.sock"


class TestIsAvailable:
    def test_false_when_no_socket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runtime = PodmanRuntime()
        monkeypatch.setattr(PodmanRuntime, "_find_socket", staticmethod(lambda: None))
        assert runtime.is_available() is False

    def test_true_when_socket_found_and_ping_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = PodmanRuntime()
        monkeypatch.setattr(
            PodmanRuntime, "_find_socket", staticmethod(lambda: "/run/podman/podman.sock")
        )
        fake_client = MagicMock()
        runtime._client = fake_client
        result = runtime.is_available()
        assert result is True
        import os

        assert os.environ["DOCKER_HOST"] == "unix:///run/podman/podman.sock"

    def test_false_when_super_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runtime = PodmanRuntime()
        monkeypatch.setattr(
            PodmanRuntime, "_find_socket", staticmethod(lambda: "/run/podman/podman.sock")
        )
        fake_client = MagicMock()
        fake_client.ping.side_effect = RuntimeError("boom")
        runtime._client = fake_client
        assert runtime.is_available() is False
