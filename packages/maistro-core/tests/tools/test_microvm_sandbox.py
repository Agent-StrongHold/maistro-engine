"""Tests for the microVM sandbox backend (SPEC-190)."""

from __future__ import annotations

from maistro.config.settings import SandboxSettings
from maistro.tools.sandbox.microvm import (
    MicroVMConfig,
    MicroVMRunSpec,
    MicroVMSandbox,
    _parse_mib,
)


class _FakeLauncher:
    def __init__(self, result: tuple[int, str] = (0, "ok")) -> None:
        self.result = result
        self.specs: list[MicroVMRunSpec] = []

    async def run(self, spec: MicroVMRunSpec) -> tuple[int, str]:
        self.specs.append(spec)
        return self.result


# An allowlisted host workspace (see tools/sandbox/workspace.ALLOWED_HOST_ROOTS).
_WS = "/tmp/maistro-workspace/vm"  # nosec B108 — test uses the sandbox allowlist root


async def test_exec_runs_command_in_microvm():
    launcher = _FakeLauncher(result=(0, "hello from vm"))
    sandbox = MicroVMSandbox(launcher, config=MicroVMConfig(memory_mib=256, vcpus=1), workspace=_WS)
    code, out = await sandbox.exec("echo hi", timeout=30)

    assert (code, out) == (0, "hello from vm")
    spec = launcher.specs[-1]
    assert spec.command == "echo hi"
    assert spec.config.network == "none"  # default-deny
    assert spec.config.memory_mib == 256 and spec.config.vcpus == 1
    assert spec.timeout == 30  # min(call, config.timeout=300)
    assert sandbox.config.vcpus == 1  # config is exposed for introspection


async def test_call_timeout_capped_by_config():
    launcher = _FakeLauncher()
    sandbox = MicroVMSandbox(launcher, config=MicroVMConfig(timeout=10), workspace=_WS)
    await sandbox.exec("echo hi", timeout=999)
    assert launcher.specs[-1].timeout == 10  # capped by the config ceiling


async def test_dangerous_command_is_blocked_before_launch():
    launcher = _FakeLauncher()
    sandbox = MicroVMSandbox(launcher, workspace=_WS)
    code, out = await sandbox.exec("rm -rf /")
    assert code == 126 and "blocked" in out
    assert launcher.specs == []  # never reached the VMM


async def test_workspace_outside_allowlist_is_blocked_before_launch():
    launcher = _FakeLauncher()
    sandbox = MicroVMSandbox(launcher, workspace="/etc")
    code, out = await sandbox.exec("echo hi")
    assert code == 126 and "workspace not permitted" in out
    assert launcher.specs == []  # a raw host path never reached the VMM


async def test_env_is_sanitized_before_launch():
    launcher = _FakeLauncher()
    sandbox = MicroVMSandbox(
        launcher,
        workspace=_WS,
        env={"PATH": "/usr/bin", "AWS_SECRET_ACCESS_KEY": "leak", "OPENAI_API_KEY": "leak"},
    )
    await sandbox.exec("echo hi")
    passed = launcher.specs[-1].env
    assert "PATH" in passed  # allowlisted
    assert "AWS_SECRET_ACCESS_KEY" not in passed and "OPENAI_API_KEY" not in passed


async def test_plain_async_function_is_a_valid_launcher():
    seen: list[MicroVMRunSpec] = []

    async def launch(spec: MicroVMRunSpec) -> tuple[int, str]:
        seen.append(spec)
        return (7, "fn-launcher")

    sandbox = MicroVMSandbox(launch, workspace=_WS)
    code, out = await sandbox.exec("echo hi")
    assert (code, out) == (7, "fn-launcher")
    assert seen[-1].workspace == _WS  # validated + resolved to the allowlisted path


def test_config_from_settings_parses_memory_and_network():
    settings = SandboxSettings(memory_limit="1g", cpu_count=4, network_disabled=False)
    config = MicroVMConfig.from_settings(settings)
    assert config.memory_mib == 1024
    assert config.vcpus == 4
    assert config.network == "restricted"


def test_from_settings_uses_vm_rootfs_not_docker_image():
    # Firecracker can't boot an OCI ref: rootfs/kernel must be the VM-specific
    # settings, never settings.image.
    settings = SandboxSettings(image="python:3.12-slim")
    config = MicroVMConfig.from_settings(settings)
    assert config.rootfs_image == "rootfs.ext4"
    assert config.kernel_image == "vmlinux"
    assert config.rootfs_image != settings.image


def test_parse_mib_units():
    assert _parse_mib("512m") == 512
    assert _parse_mib("2g") == 2048
    assert _parse_mib("1024k") == 1
    assert _parse_mib("2097152") == 2  # bare bytes -> MiB
    assert _parse_mib("500") == 1  # rounds up to a 1 MiB floor
