"""Security-focused tests for the live Builders isolated workspace path."""

from __future__ import annotations

from pathlib import Path

import pytest

from maistro.builders.isolated_workspace import IsolatedBuilderSandbox, validate_repo_url
from maistro.builders.session_store import BuilderSessionStore
from maistro.sandbox.protocol import ExecResult, SandboxConfig, SandboxInstance
from maistro.sandbox.selector import SandboxSelector

BASE_COMMIT = "a" * 40


class RecordingVmBackend:
    def __init__(self) -> None:
        self.configs: list[SandboxConfig] = []
        self.commands: list[tuple[str, list[str]]] = []
        self.files: dict[tuple[str, str], bytes] = {}
        self.destroyed: list[str] = []

    async def spawn(self, *, config: SandboxConfig) -> SandboxInstance:
        self.configs.append(config)
        instance_id = f"vm-{len(self.configs)}"
        return SandboxInstance(
            id=instance_id,
            backend="recording-vm",
            isolation_tier="vm",
            metadata={"network": config.network, "workspace_path": config.workspace_path},
        )

    async def exec(
        self, instance: SandboxInstance, command: list[str], *, timeout_s: int = 120
    ) -> ExecResult:
        self.commands.append((instance.id, command))
        stdout = ""
        if command[:3] == ["stat", "-c", "%s"]:
            stdout = "7\n"
        elif command[-2:] == ["rev-parse", "HEAD"]:
            stdout = f"{BASE_COMMIT}\n"
        elif command == ["git", "--version"]:
            stdout = "git version 2.54.0\n"
        elif command[:2] == ["git", "diff"]:
            stdout = "diff --git a/a.txt b/a.txt\n"
        return ExecResult(exit_code=0, stdout=stdout, stderr="", duration_ms=1)

    async def write_file(self, instance: SandboxInstance, path: str, content: bytes) -> None:
        self.files[(instance.id, path)] = content

    async def read_file(self, instance: SandboxInstance, path: str) -> bytes:
        if path.endswith(".tar"):  # UUID-named archive; path changes per call
            return b"archive"
        return self.files[(instance.id, path)]

    async def destroy(self, instance: SandboxInstance) -> None:
        self.destroyed.append(instance.id)


def _selector(backend: RecordingVmBackend) -> SandboxSelector:
    selector = SandboxSelector()
    selector.register("vm", backend)
    return selector


def test_create_materializes_in_networked_vm_then_runs_offline() -> None:
    backend = RecordingVmBackend()
    sandbox = IsolatedBuilderSandbox.create(
        "https://github.com/acme/widget.git",
        selector=_selector(backend),
    )
    try:
        assert [config.network for config in backend.configs] == [True, False]
        assert backend.destroyed == ["vm-1"]
        clone = next(command for _, command in backend.commands if "clone" in command)
        assert "GIT_TERMINAL_PROMPT=0" in clone
        assert "http.followRedirects=false" in clone
        assert "--no-recurse-submodules" in clone
        assert sandbox.isolation_tier == "vm"
        assert sandbox.base_commit == BASE_COMMIT
        assert sandbox.git_version == "git version 2.54.0"
        assert any(
            command[-2:] == ["remote.origin.pushurl", "maistro-disabled://push"]
            for _, command in backend.commands
        )
    finally:
        sandbox.close()
    assert backend.destroyed == ["vm-1", "vm-2"]


def test_replay_patch_is_applied_only_in_offline_vm() -> None:
    backend = RecordingVmBackend()
    sandbox = IsolatedBuilderSandbox.create(
        "https://github.com/acme/widget",
        patch="diff --git a/a.txt b/a.txt\n",
        selector=_selector(backend),
    )
    try:
        replay_key = next(
            k for k in backend.files if k[0] == "vm-2" and "maistro-replay" in k[1]
        )
        assert backend.files[replay_key].startswith(b"diff --git")
        apply_instance, apply_command = next(
            item for item in backend.commands if item[1][:2] == ["git", "apply"]
        )
        assert apply_instance == "vm-2"
        assert backend.configs[1].network is False
        assert replay_key[1] in apply_command
    finally:
        sandbox.close()


def test_full_shell_syntax_runs_only_inside_offline_vm() -> None:
    backend = RecordingVmBackend()
    sandbox = IsolatedBuilderSandbox.create(
        "https://github.com/acme/widget",
        selector=_selector(backend),
    )
    try:
        sandbox.run_command("printf hello | grep hello > result.txt")
        instance_id, command = backend.commands[-1]
        assert instance_id == "vm-2"
        assert command == ["sh", "-lc", "printf hello | grep hello > result.txt"]
        assert backend.configs[1].network is False
    finally:
        sandbox.close()


def test_fixed_file_management_tools_run_only_inside_offline_vm() -> None:
    backend = RecordingVmBackend()
    sandbox = IsolatedBuilderSandbox.create(
        "https://github.com/acme/widget",
        selector=_selector(backend),
    )
    try:
        sandbox.delete_file("obsolete.txt")
        sandbox.list_files(glob="src/**/*.py", limit=50)
        delete_instance, delete_command = backend.commands[-2]
        list_instance, list_command = backend.commands[-1]
        assert delete_instance == list_instance == "vm-2"
        assert delete_command == ["rm", "-f", "--", "/workspace/obsolete.txt"]
        assert list_command[-2:] == ["src/**/*.py", "50"]
        with pytest.raises(ValueError, match="Git metadata"):
            sandbox.list_files(glob=".git/**/*")
    finally:
        sandbox.close()


def test_candidate_patch_is_applied_only_in_offline_vm() -> None:
    backend = RecordingVmBackend()
    sandbox = IsolatedBuilderSandbox.create(
        "https://github.com/acme/widget",
        selector=_selector(backend),
    )
    try:
        sandbox.apply_patch("diff --git a/a.txt b/a.txt\n")
        apply_instance, apply_command = next(
            item
            for item in reversed(backend.commands)
            if item[1][:2] == ["git", "apply"]
        )
        assert apply_instance == "vm-2"
        assert backend.configs[1].network is False
        patch_path = apply_command[-1]
        assert "maistro-patch" in patch_path and patch_path.endswith(".patch")
        assert backend.files[("vm-2", patch_path)].startswith(b"diff --git")
    finally:
        sandbox.close()


@pytest.mark.parametrize(
    "url",
    [
        "/local/repo",
        "file:///tmp/repo",
        "ssh://git@github.com/acme/repo",
        "https://token@github.com/acme/repo",
        "https://github.com:8443/acme/repo",
        "https://example.com/acme/repo",
    ],
)
def test_repo_url_validation_rejects_unsafe_sources(url: str) -> None:
    with pytest.raises(ValueError):
        validate_repo_url(url)


def test_session_store_replays_only_repo_and_patch(tmp_path: Path) -> None:
    store = BuilderSessionStore(tmp_path)
    saved = store.save(
        session_id="widget-abcd1234",
        repo_url="https://github.com/acme/widget",
        base_commit=BASE_COMMIT,
        patch="diff --git a/a.txt b/a.txt\n",
    )

    assert saved.repo_url == "https://github.com/acme/widget"
    assert store.load_patch(saved.session_id).startswith("diff --git")
    assert store.list_sessions() == [saved]
    assert set((tmp_path / saved.session_id).iterdir()) == {
        tmp_path / saved.session_id / "changes.patch",
        tmp_path / saved.session_id / "session.json",
    }


def test_session_store_rejects_path_escape(tmp_path: Path) -> None:
    store = BuilderSessionStore(tmp_path)
    with pytest.raises(ValueError, match="Invalid Builders session ID"):
        store.save(
            session_id="../escape",
            repo_url="https://github.com/acme/widget",
            base_commit=BASE_COMMIT,
            patch="",
        )
