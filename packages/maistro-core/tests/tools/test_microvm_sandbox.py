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


async def test_exec_runs_command_in_microvm():
    launcher = _FakeLauncher(result=(0, "hello from vm"))
    sandbox = MicroVMSandbox(
        launcher,
        config=MicroVMConfig(memory_mib=256, vcpus=1),
        workspace="/tmp/maistro-workspace/t1",
    )
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
    sandbox = MicroVMSandbox(
        launcher, config=MicroVMConfig(timeout=10), workspace="/tmp/maistro-workspace/t2"
    )
    await sandbox.exec("echo hi", timeout=999)
    assert launcher.specs[-1].timeout == 10  # capped by the config ceiling


async def test_dangerous_command_is_blocked_before_launch():
    launcher = _FakeLauncher()
    sandbox = MicroVMSandbox(launcher, workspace="/tmp/maistro-workspace/t3")
    code, out = await sandbox.exec("rm -rf /")
    assert code == 126 and "blocked" in out
    assert launcher.specs == []  # never reached the VMM


async def test_plain_async_function_is_a_valid_launcher():
    seen: list[MicroVMRunSpec] = []

    async def launch(spec: MicroVMRunSpec) -> tuple[int, str]:
        seen.append(spec)
        return (7, "fn-launcher")

    sandbox = MicroVMSandbox(launch, workspace="/tmp/maistro-workspace/t4")
    code, out = await sandbox.exec("echo hi")
    assert (code, out) == (7, "fn-launcher")
    assert seen[-1].workspace == "/tmp/maistro-workspace/t4"


def test_config_from_settings_parses_memory_and_network():
    settings = SandboxSettings(memory_limit="1g", cpu_count=4, network_disabled=False)
    config = MicroVMConfig.from_settings(settings)
    assert config.memory_mib == 1024
    assert config.vcpus == 4
    assert config.network == "restricted"


def test_parse_mib_units():
    assert _parse_mib("512m") == 512
    assert _parse_mib("2g") == 2048
    assert _parse_mib("1024k") == 1
    assert _parse_mib("2097152") == 2  # bare bytes -> MiB
    assert _parse_mib("500") == 1  # rounds up to a 1 MiB floor


def test_workspace_outside_allowlist_is_refused():
    """The harness API's request body controls workdir, and the launcher
    mounts it into the guest: /etc or the service checkout must be refused at
    construction, mirroring the Docker backend's ensure_workspace posture."""
    import pytest

    async def launch(spec):
        return 0, ""

    for hostile in ("/etc", "/", "/home", "."):
        with pytest.raises(ValueError):
            MicroVMSandbox(launch, workspace=hostile)
