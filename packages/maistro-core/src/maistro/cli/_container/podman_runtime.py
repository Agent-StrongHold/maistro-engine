"""Podman runtime implementation.

Uses the Docker-compatible API exposed by Podman's socket.
Most operations are identical to DockerRuntime; the differences
are in socket discovery and availability checks.
"""

from __future__ import annotations

import os

from maistro.cli._container.docker_runtime import DockerRuntime


class PodmanRuntime(DockerRuntime):
    """ContainerRuntime via Podman's Docker-compatible socket.

    Podman exposes a Docker-compatible API at:
      - $XDG_RUNTIME_DIR/podman/podman.sock (rootless)
      - /run/podman/podman.sock (rootful)
    """

    def is_available(self) -> bool:
        sock = self._find_socket()
        if sock is None:
            return False

        os.environ["DOCKER_HOST"] = f"unix://{sock}"
        try:
            return super().is_available()
        except (
            Exception
        ):  # pragma: no cover — DockerRuntime.is_available() already swallows all exceptions
            return False

    @staticmethod
    def _find_socket() -> str | None:
        candidates = [
            os.path.join(
                os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
                "podman",
                "podman.sock",
            ),
            "/run/podman/podman.sock",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None
