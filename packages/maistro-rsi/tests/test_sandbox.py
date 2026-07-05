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


class TestLocalSandbox:
    """Tests tied to SPEC.md §1 acceptance criteria sandbox-8..12."""

    def test_satisfies_microvm_protocol(self, tmp_path):
        """sandbox-8: LocalSandbox structurally satisfies MicroVmSandbox."""
        from maistro_rsi.sandbox.local import LocalSandbox

        assert isinstance(LocalSandbox(str(tmp_path)), MicroVmSandbox)

    @pytest.mark.asyncio
    async def test_exec_returns_exit_code_and_output(self, tmp_path):
        """sandbox-9: exec runs against the workspace and returns (exit_code, output)."""
        from maistro_rsi.sandbox.local import LocalSandbox

        sandbox = LocalSandbox(str(tmp_path))
        code, output = await sandbox.exec("echo hello")
        assert code == 0 and "hello" in output

    @pytest.mark.asyncio
    async def test_exec_reports_nonzero_exit_verbatim(self, tmp_path):
        """sandbox-9: a non-zero exit is reported, not swallowed."""
        from maistro_rsi.sandbox.local import LocalSandbox

        code, _ = await LocalSandbox(str(tmp_path)).exec("exit 3")
        assert code == 3

    @pytest.mark.asyncio
    async def test_exec_times_out_and_reports_124(self, tmp_path):
        """sandbox-9: a command exceeding the timeout is killed and reported as exit 124."""
        from maistro_rsi.sandbox.local import LocalSandbox

        code, output = await LocalSandbox(str(tmp_path)).exec("sleep 30", timeout=1)
        assert code == 124 and "timeout" in output

    @pytest.mark.asyncio
    async def test_write_read_round_trip_relative_path_stays_in_workspace(self, tmp_path):
        """sandbox-10: write/read round-trip; relative paths resolve under the workspace."""
        from maistro_rsi.sandbox.local import LocalSandbox

        sandbox = LocalSandbox(str(tmp_path))
        await sandbox.write_file("sub/notes.txt", "hi")
        assert await sandbox.read_file("sub/notes.txt") == "hi"
        assert (tmp_path / "sub" / "notes.txt").read_text() == "hi"

    @pytest.mark.asyncio
    async def test_snapshot_unique_and_restore_posture(self, tmp_path):
        """sandbox-11: unique snapshot ids; restore raises KeyError / NotImplementedError."""
        from maistro_rsi.sandbox.local import LocalSandbox

        sandbox = LocalSandbox(str(tmp_path))
        a = await sandbox.snapshot("cp")
        b = await sandbox.snapshot("cp")
        assert a != b
        with pytest.raises(KeyError):
            await sandbox.restore("never")
        with pytest.raises(NotImplementedError):
            await sandbox.restore(a)

    @pytest.mark.asyncio
    async def test_destroy_is_noop_and_context_manager_exits_clean(self, tmp_path):
        """sandbox-12: destroy never raises; async-with exits cleanly."""
        from maistro_rsi.sandbox.local import LocalSandbox

        async with LocalSandbox(str(tmp_path)) as sandbox:
            await sandbox.write_file("f", "x")
        await sandbox.destroy()  # idempotent, no raise


class TestCreateRsiSandbox:
    """Tests tied to SPEC.md §1 acceptance criterion sandbox-13."""

    @pytest.mark.asyncio
    async def test_local_backend_selected_by_arg(self, tmp_path):
        """sandbox-13: backend='local' returns a LocalSandbox."""
        from maistro_rsi.sandbox.local import LocalSandbox
        from maistro_rsi.sandbox.microvm import create_rsi_sandbox

        sandbox = await create_rsi_sandbox(str(tmp_path), backend="local")
        assert isinstance(sandbox, LocalSandbox)

    @pytest.mark.asyncio
    async def test_local_backend_selected_by_env(self, tmp_path, monkeypatch):
        """sandbox-13: $MAISTRO_RSI_SANDBOX=local returns a LocalSandbox."""
        from maistro_rsi.sandbox.local import LocalSandbox
        from maistro_rsi.sandbox.microvm import SANDBOX_BACKEND_ENV, create_rsi_sandbox

        monkeypatch.setenv(SANDBOX_BACKEND_ENV, "local")
        assert isinstance(await create_rsi_sandbox(str(tmp_path)), LocalSandbox)

    @pytest.mark.asyncio
    async def test_arg_overrides_env_and_default_is_docker(self, tmp_path, monkeypatch):
        """sandbox-13: explicit backend arg overrides env; default routes to the Docker backend."""
        import maistro_rsi.sandbox.microvm as microvm_mod
        from maistro_rsi.sandbox.local import LocalSandbox

        # env says docker, arg says local → arg wins
        monkeypatch.setenv(microvm_mod.SANDBOX_BACKEND_ENV, "docker")
        assert isinstance(
            await microvm_mod.create_rsi_sandbox(str(tmp_path), backend="local"), LocalSandbox
        )

        # default (no arg, no env) routes to create_microvm_sandbox — stub it so
        # the test needs no real Docker daemon.
        monkeypatch.delenv(microvm_mod.SANDBOX_BACKEND_ENV, raising=False)
        sentinel = object()

        async def fake_create(workspace, settings=None, env=None):
            return sentinel

        monkeypatch.setattr(microvm_mod, "create_microvm_sandbox", fake_create)
        assert await microvm_mod.create_rsi_sandbox(str(tmp_path)) is sentinel
