"""Secure Builders workspace backed by the central sandbox protocol."""

from __future__ import annotations

import asyncio
import os
import re
import threading
from collections.abc import Coroutine
from pathlib import PurePosixPath
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit

from maistro.sandbox.factory import build_default_selector
from maistro.sandbox.policy import REPO_MATERIALIZATION, UNTRUSTED_CODE
from maistro.sandbox.protocol import ExecResult, SandboxInstance, SandboxProtocol
from maistro.sandbox.selector import SandboxSelector

_DEFAULT_TIMEOUT = 30
_OUTPUT_CAP = 1 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_MAX_PATCH_BYTES = 32 * 1024 * 1024
_WORKSPACE = PurePosixPath("/workspace")
_ARCHIVE = "/tmp/maistro-repo.tar"
_BLOCKED_PATTERNS = ("sudo", "git push", "git force", "mount ", "umount ", "mkfs", "dd if=")
_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")
_GIT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
_GIT_VERSION = re.compile(r"^git version [0-9]+(?:\.[0-9]+){1,3}(?:[.\-+A-Za-z0-9]*)$")

T = TypeVar("T")


class _AsyncBridge:
    """Run async sandbox protocol calls from the synchronous agent tool API."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._closed = False

    def call(self, coroutine: Coroutine[Any, Any, T]) -> T:
        if self._closed:
            coroutine.close()
            raise RuntimeError("Sandbox bridge is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()


class IsolatedBuilderSandbox:
    """Synchronous BuilderSandbox adapter over a VM-grade SandboxProtocol backend.

    Repository materialization happens in a temporary networked VM. Its archive
    is copied into a separate network-disabled execution VM before any agent
    command runs.
    """

    def __init__(
        self,
        *,
        backend: SandboxProtocol,
        instance: SandboxInstance,
        bridge: _AsyncBridge,
        base_commit: str,
    ) -> None:
        if instance.isolation_tier != "vm":
            raise ValueError("Builders requires a VM-grade sandbox instance")
        if bool(instance.metadata.get("network")):
            raise ValueError("Builders execution instance must have network disabled")
        self._backend = backend
        self._instance = instance
        self._bridge = bridge
        self._base_commit = base_commit
        self._closed = False

    @classmethod
    def create(  # noqa: C901 - materialization cleanup is intentionally kept in one boundary
        cls,
        repo_url: str,
        *,
        patch: str | None = None,
        base_commit: str | None = None,
        base_ref: str | None = None,
        selector: SandboxSelector | None = None,
        image_ref: str | None = None,
    ) -> IsolatedBuilderSandbox:
        """Clone a public HTTPS repository and return an offline VM workspace."""
        validated_url = validate_repo_url(repo_url)
        if base_commit is not None and not _COMMIT_SHA.fullmatch(base_commit):
            raise ValueError("Builders replay base commit must be a full hexadecimal object ID")
        if base_ref is not None:
            validate_git_ref(base_ref)
        active_selector = selector or build_default_selector()
        _, materializer_backend = active_selector.select(REPO_MATERIALIZATION)
        _, execution_backend = active_selector.select(UNTRUSTED_CODE)
        bridge = _AsyncBridge()
        image = image_ref or os.environ.get("MAISTRO_BUILDERS_IMAGE", "maistro-builders:latest")
        materializer: SandboxInstance | None = None
        execution: SandboxInstance | None = None

        try:
            materializer_config = active_selector.build_config(
                REPO_MATERIALIZATION,
                image_ref=image,
                network=True,
                lifetime_s=900,
                writable_paths=["/workspace", "/tmp"],
            )
            materializer = bridge.call(materializer_backend.spawn(config=materializer_config))
            _checked_exec(
                bridge,
                materializer_backend,
                materializer,
                ["mkdir", "-p", "/tmp/empty-git-template"],
            )
            clone_command = [
                "env",
                "GIT_CONFIG_NOSYSTEM=1",
                "GIT_TERMINAL_PROMPT=0",
                "git",
                "-c",
                "credential.helper=",
                "-c",
                "protocol.file.allow=never",
                "-c",
                "http.followRedirects=false",
                "clone",
                "--no-recurse-submodules",
                "--depth=1",
                "--single-branch",
                "--template=/tmp/empty-git-template",
            ]
            if base_ref is not None:
                clone_command.extend(["--branch", base_ref])
            clone_command.extend(["--", validated_url, "/workspace/repo"])
            _checked_exec(
                bridge,
                materializer_backend,
                materializer,
                clone_command,
                timeout_s=600,
            )
            if base_commit is not None:
                _checked_exec(
                    bridge,
                    materializer_backend,
                    materializer,
                    [
                        "env",
                        "GIT_CONFIG_NOSYSTEM=1",
                        "GIT_TERMINAL_PROMPT=0",
                        "git",
                        "-C",
                        "/workspace/repo",
                        "-c",
                        "credential.helper=",
                        "-c",
                        "protocol.file.allow=never",
                        "-c",
                        "http.followRedirects=false",
                        "fetch",
                        "--depth=1",
                        "--no-recurse-submodules",
                        "origin",
                        base_commit,
                    ],
                    timeout_s=600,
                )
                _checked_exec(
                    bridge,
                    materializer_backend,
                    materializer,
                    ["git", "-C", "/workspace/repo", "checkout", "--detach", base_commit],
                    timeout_s=300,
                )
            resolved_base = _checked_exec(
                bridge,
                materializer_backend,
                materializer,
                ["git", "-C", "/workspace/repo", "rev-parse", "HEAD"],
            ).stdout.strip()
            if not _COMMIT_SHA.fullmatch(resolved_base):
                raise RuntimeError("Sandbox returned an invalid base commit object ID")
            _checked_exec(
                bridge,
                materializer_backend,
                materializer,
                ["tar", "-C", "/workspace/repo", "-cf", _ARCHIVE, "."],
                timeout_s=300,
            )
            archive_size = _checked_exec(
                bridge,
                materializer_backend,
                materializer,
                ["stat", "-c", "%s", _ARCHIVE],
            )
            try:
                size_bytes = int(archive_size.stdout.strip())
            except ValueError as exc:
                raise RuntimeError("Sandbox returned an invalid repository archive size") from exc
            if size_bytes > _MAX_ARCHIVE_BYTES:
                raise ValueError(
                    f"Repository archive exceeds the {_MAX_ARCHIVE_BYTES}-byte Builders limit"
                )
            archive = bridge.call(materializer_backend.read_file(materializer, _ARCHIVE))
            bridge.call(materializer_backend.destroy(materializer))
            materializer = None

            execution_config = active_selector.build_config(
                UNTRUSTED_CODE,
                image_ref=image,
                network=False,
                lifetime_s=21600,
                writable_paths=["/workspace", "/tmp"],
            )
            execution = bridge.call(execution_backend.spawn(config=execution_config))
            bridge.call(execution_backend.write_file(execution, _ARCHIVE, archive))
            _checked_exec(
                bridge,
                execution_backend,
                execution,
                ["tar", "-C", "/workspace", "-xf", _ARCHIVE],
                timeout_s=300,
            )
            _checked_exec(
                bridge,
                execution_backend,
                execution,
                ["rm", "--", _ARCHIVE],
            )
            _harden_git_config(bridge, execution_backend, execution)
            execution.metadata["base_commit"] = resolved_base
            git_version = _checked_exec(
                bridge,
                execution_backend,
                execution,
                ["git", "--version"],
            ).stdout.strip()
            if not _GIT_VERSION.fullmatch(git_version):
                raise RuntimeError("Sandbox returned an invalid Git runtime version")
            execution.metadata["git_version"] = git_version
            if patch:
                bridge.call(
                    execution_backend.write_file(
                        execution,
                        "/tmp/maistro-replay.patch",
                        patch.encode("utf-8"),
                    )
                )
                _checked_exec(
                    bridge,
                    execution_backend,
                    execution,
                    ["git", "apply", "--binary", "--whitespace=nowarn", "/tmp/maistro-replay.patch"],
                    timeout_s=300,
                )
                _checked_exec(
                    bridge,
                    execution_backend,
                    execution,
                    ["rm", "--", "/tmp/maistro-replay.patch"],
                )
            return cls(
                backend=execution_backend,
                instance=execution,
                bridge=bridge,
                base_commit=resolved_base,
            )
        except Exception:
            if materializer is not None:
                bridge.call(materializer_backend.destroy(materializer))
            if execution is not None:
                bridge.call(execution_backend.destroy(execution))
            bridge.close()
            raise

    @property
    def isolation_tier(self) -> str:
        return cast(str, self._instance.isolation_tier)

    @property
    def backend_name(self) -> str:
        return cast(str, self._instance.backend)

    @property
    def base_commit(self) -> str:
        return self._base_commit

    @property
    def git_version(self) -> str:
        return str(self._instance.metadata["git_version"])

    def read_file(self, path: str) -> str:
        self._require_open()
        target = self._workspace_path(path)
        data = cast(bytes, self._bridge.call(self._backend.read_file(self._instance, target)))
        return data.decode(
            "utf-8", errors="replace"
        )

    def write_file(self, path: str, content: str) -> None:
        self._require_open()
        target = self._workspace_path(path)
        self._bridge.call(self._backend.write_file(self._instance, target, content.encode("utf-8")))

    def delete_file(self, path: str) -> None:
        self._require_open()
        target = self._workspace_path(path)
        result = self._exec(["rm", "-f", "--", target])
        if result.exit_code != 0 or result.timed_out:
            raise RuntimeError(f"Failed to delete Builders file: {_result_output(result)}")

    def run_command(self, cmd: str, *, timeout: int = _DEFAULT_TIMEOUT) -> str:
        return _result_output(self.run_command_result(cmd, timeout=timeout))

    def run_command_result(self, cmd: str, *, timeout: int = _DEFAULT_TIMEOUT) -> ExecResult:
        lowered = cmd.lower()
        for pattern in _BLOCKED_PATTERNS:
            if pattern in lowered:
                raise ValueError(f"Blocked Builders command pattern: {pattern!r}")
        return self._exec(["sh", "-lc", cmd], timeout=timeout)

    def run_argv(self, argv: list[str], *, timeout: int = _DEFAULT_TIMEOUT) -> str:
        return _result_output(self._exec(argv, timeout=timeout))

    def apply_patch(self, patch: str) -> None:
        """Apply a bounded unified diff inside the offline execution VM."""
        self._require_open()
        patch_bytes = patch.encode("utf-8")
        if len(patch_bytes) > _MAX_PATCH_BYTES:
            raise ValueError(f"Builders candidate patch exceeds {_MAX_PATCH_BYTES} bytes")
        patch_path = "/tmp/maistro-candidate.patch"
        self._bridge.call(self._backend.write_file(self._instance, patch_path, patch_bytes))
        try:
            result = self._exec(
                ["git", "apply", "--binary", "--whitespace=nowarn", patch_path],
                timeout=300,
            )
            if result.exit_code != 0 or result.timed_out:
                raise RuntimeError(f"Failed to apply Builders candidate patch: {_result_output(result)}")
        finally:
            self._exec(["rm", "-f", "--", patch_path])

    def _exec(self, argv: list[str], *, timeout: int = _DEFAULT_TIMEOUT) -> ExecResult:
        self._require_open()
        return self._bridge.call(self._backend.exec(self._instance, argv, timeout_s=timeout))

    def diff(self) -> str:
        intent = self._exec(["git", "add", "--intent-to-add", "--all", "--", "."])
        if intent.exit_code != 0 or intent.timed_out:
            raise RuntimeError(f"Failed to prepare Builders replay diff: {_result_output(intent)}")
        result = self._exec(
            [
                "git",
                "diff",
                "--binary",
                "--no-ext-diff",
                "--no-textconv",
                self._base_commit,
                "--",
            ]
        )
        if result.exit_code != 0 or result.timed_out:
            raise RuntimeError(f"Failed to export Builders replay diff: {_result_output(result)}")
        return cast(str, result.stdout)

    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]:
        script = (
            "from pathlib import Path; import sys; "
            "root=Path('.'); pattern=sys.argv[1]; glob=sys.argv[2]; "
            "print('\\n'.join(str(p) for p in root.glob(glob) "
            "if p.is_file() and pattern in p.read_text(encoding='utf-8', errors='ignore')))"
        )
        output = self.run_argv(["python", "-c", script, pattern, glob], timeout=120)
        return [line for line in output.splitlines() if line]

    def list_files(self, *, glob: str = "**/*", limit: int = 2000) -> list[str]:
        if limit < 1 or limit > 10_000:
            raise ValueError("Builders file listing limit must be between 1 and 10000")
        parsed = PurePosixPath(glob)
        if parsed.is_absolute() or ".." in parsed.parts or ".git" in parsed.parts:
            raise ValueError(f"Builders file glob must stay outside Git metadata: {glob!r}")
        script = (
            "from pathlib import Path; import sys; "
            "root=Path('.'); glob=sys.argv[1]; limit=int(sys.argv[2]); "
            "paths=(p for p in root.glob(glob) if p.is_file() and '.git' not in p.parts); "
            "print('\\n'.join(str(p) for _, p in zip(range(limit), paths, strict=False)))"
        )
        output = self.run_argv(["python", "-c", script, glob, str(limit)], timeout=120)
        return [line for line in output.splitlines() if line]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._bridge.call(self._backend.destroy(self._instance))
        finally:
            self._bridge.close()

    def __enter__(self) -> IsolatedBuilderSandbox:
        self._require_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Builders sandbox is closed")

    @staticmethod
    def _workspace_path(path: str) -> str:
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or str(parsed) in {"", "."}:
            raise ValueError(f"Builders file path must stay inside the workspace: {path!r}")
        return str(_WORKSPACE / parsed)


def validate_repo_url(repo_url: str) -> str:
    """Allow only credential-free HTTPS URLs to explicitly approved git hosts."""
    parsed = urlsplit(repo_url.strip())
    hosts = {
        host.strip().lower()
        for host in os.environ.get(
            "MAISTRO_BUILDERS_GIT_HOSTS", "github.com,gitlab.com,bitbucket.org"
        ).split(",")
        if host.strip()
    }
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Secure Builders accepts HTTPS repository URLs only")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Repository URLs must not contain credentials, query strings, or fragments")
    if parsed.port not in {None, 443}:
        raise ValueError("Repository URLs must use the default HTTPS port")
    if parsed.hostname.lower() not in hosts:
        raise ValueError(
            f"Repository host {parsed.hostname!r} is not approved; "
            "configure MAISTRO_BUILDERS_GIT_HOSTS to add it"
        )
    if parsed.path in {"", "/"}:
        raise ValueError("Repository URL must include an owner and repository path")
    return repo_url.strip()


def validate_git_ref(ref: str) -> str:
    """Accept a conservative branch/tag name for the networked clone step."""
    if (
        not _GIT_REF.fullmatch(ref)
        or ".." in ref
        or "@{" in ref
        or ref.endswith((".", "/"))
        or "//" in ref
    ):
        raise ValueError(f"Unsafe Git ref: {ref!r}")
    return ref


def _checked_exec(
    bridge: _AsyncBridge,
    backend: SandboxProtocol,
    instance: SandboxInstance,
    command: list[str],
    *,
    timeout_s: int = _DEFAULT_TIMEOUT,
) -> ExecResult:
    result = bridge.call(backend.exec(instance, command, timeout_s=timeout_s))
    if result.exit_code != 0 or result.timed_out:
        raise RuntimeError(f"Sandbox command failed: {command[0]!r}: {_result_output(result)}")
    return result


def _harden_git_config(
    bridge: _AsyncBridge,
    backend: SandboxProtocol,
    instance: SandboxInstance,
) -> None:
    _checked_exec(bridge, backend, instance, ["mkdir", "-p", "/tmp/maistro-disabled-hooks"])
    settings = (
        ("core.hooksPath", "/tmp/maistro-disabled-hooks"),
        ("credential.helper", ""),
        ("protocol.file.allow", "never"),
        ("submodule.recurse", "false"),
        ("remote.origin.pushurl", "maistro-disabled://push"),
        ("protocol.maistro-disabled.allow", "never"),
        ("user.name", "Maistro Builder"),
        ("user.email", "builder@invalid"),
    )
    for key, value in settings:
        _checked_exec(bridge, backend, instance, ["git", "config", "--local", key, value])


def _result_output(result: ExecResult) -> str:
    output = f"{result.stdout}{result.stderr}"
    if len(output) > _OUTPUT_CAP:
        return output[:_OUTPUT_CAP]
    return output
