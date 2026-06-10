"""Tests tied to SPEC.md §1 (MicroVM sandbox) acceptance criteria sandbox-1..7."""

from __future__ import annotations

import pytest

from maistro_rsi.protocols import MicroVmSandbox
from maistro_rsi.sandbox.microvm import DockerMicroVmSandbox


class FakeContainer:
    def __init__(self) -> None:
        self.destroy_calls = 0
        self.files: dict[str, str] = {}

    async def exec(self, command, timeout=60):
        return 0, f"ran: {command}"

    async def read_file(self, path):
        return self.files[path]

    async def write_file(self, path, content):
        self.files[path] = content

    async def destroy(self):
        self.destroy_calls += 1


class TestDockerMicroVmSandbox:
    def test_satisfies_microvm_protocol(self):
        """sandbox-1: DockerMicroVmSandbox structurally satisfies MicroVmSandbox."""
        sandbox = DockerMicroVmSandbox(FakeContainer())
        assert isinstance(sandbox, MicroVmSandbox)

    @pytest.mark.asyncio
    async def test_exec_delegates_to_container_and_returns_exit_code_and_output(self):
        """sandbox-2: exec runs the command and returns (exit_code, output)."""
        sandbox = DockerMicroVmSandbox(FakeContainer())
        code, output = await sandbox.exec("echo hi")
        assert code == 0
        assert "echo hi" in output

    @pytest.mark.asyncio
    async def test_write_then_read_round_trips_through_workspace(self):
        """sandbox-3: write_file followed by read_file round-trips content."""
        sandbox = DockerMicroVmSandbox(FakeContainer())
        await sandbox.write_file("notes.txt", "hello")
        assert await sandbox.read_file("notes.txt") == "hello"

    @pytest.mark.asyncio
    async def test_snapshot_ids_are_unique_even_for_the_same_label(self):
        """sandbox-4: snapshot returns a unique id per call, no collisions."""
        sandbox = DockerMicroVmSandbox(FakeContainer())
        snap_a = await sandbox.snapshot("checkpoint")
        snap_b = await sandbox.snapshot("checkpoint")
        assert snap_a != snap_b

    @pytest.mark.asyncio
    async def test_restore_of_captured_snapshot_raises_not_implemented(self):
        """sandbox-5: restoring a real snapshot id raises NotImplementedError, not a silent no-op."""
        sandbox = DockerMicroVmSandbox(FakeContainer())
        snapshot_id = await sandbox.snapshot("checkpoint")
        with pytest.raises(NotImplementedError):
            await sandbox.restore(snapshot_id)

    @pytest.mark.asyncio
    async def test_restore_of_unknown_snapshot_raises_key_error(self):
        """sandbox-5: restoring an id that was never captured raises KeyError."""
        sandbox = DockerMicroVmSandbox(FakeContainer())
        with pytest.raises(KeyError):
            await sandbox.restore("never-captured")

    @pytest.mark.asyncio
    async def test_destroy_tears_down_the_underlying_container_exactly_once(self):
        """sandbox-6: destroy() tears down the container exactly once."""
        container = FakeContainer()
        sandbox = DockerMicroVmSandbox(container)
        await sandbox.destroy()
        assert container.destroy_calls == 1

    @pytest.mark.asyncio
    async def test_async_context_manager_destroys_on_normal_exit(self):
        """sandbox-7: async-with destroys the sandbox on normal exit."""
        container = FakeContainer()
        async with DockerMicroVmSandbox(container):
            assert container.destroy_calls == 0
        assert container.destroy_calls == 1

    @pytest.mark.asyncio
    async def test_async_context_manager_destroys_on_exception(self):
        """sandbox-7: async-with destroys the sandbox even when the body raises — no leaked containers."""
        container = FakeContainer()
        with pytest.raises(RuntimeError):
            async with DockerMicroVmSandbox(container):
                raise RuntimeError("boom")
        assert container.destroy_calls == 1
