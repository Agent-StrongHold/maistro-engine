"""Unit tests for the Kata VM backend command boundary."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from maistro.sandbox.backends.kata import KataSandboxBackend
from maistro.sandbox.protocol import SandboxConfig


def test_runtime_name_must_identify_kata() -> None:
    with pytest.raises(ValueError, match="Kata"):
        KataSandboxBackend(runtime="runc")


def test_availability_requires_configured_kata_runtime() -> None:
    backend = KataSandboxBackend(engine="docker", runtime="kata-runtime")
    result = Mock(returncode=0, stdout=json.dumps({"runc": {}, "kata-runtime": {}}))
    with patch("subprocess.run", return_value=result) as run:
        assert backend.is_available() is True
    run.assert_called_once()


@pytest.mark.asyncio
async def test_spawn_uses_vm_runtime_without_host_mounts_or_network() -> None:
    backend = KataSandboxBackend(engine="docker", runtime="kata-runtime")
    captured: list[str] = []

    async def fake_run(
        command: list[str], *, input_data: bytes | None = None, timeout_s: int
    ) -> tuple[int, bytes, bytes]:
        captured.extend(command)
        return 0, b"container-id\n", b""

    backend._run = fake_run  # type: ignore[method-assign]
    instance = await backend.spawn(
        config=SandboxConfig(
            image_ref="builders@sha256:test",
            network=False,
            min_isolation="vm",
        )
    )

    assert instance.isolation_tier == "vm"
    runtime_position = captured.index("--runtime")
    assert captured[runtime_position : runtime_position + 2] == ["--runtime", "kata-runtime"]
    assert "--network=none" in captured
    assert "--read-only" in captured
    assert "--cap-drop=ALL" in captured
    assert "-v" not in captured
    assert "--volume" not in captured
