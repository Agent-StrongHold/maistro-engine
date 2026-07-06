"""``opencode`` harness_runner provider (SPEC-208 §1-2).

Drives `opencode <https://opencode.ai>`_ (``sst/opencode``, an open-source
terminal coding agent) as a foreign harness. Each turn is a non-interactive
``opencode run`` executed inside the injected sandbox, pointed at the caller's
repo/workdir — so opencode edits a real checkout under OS isolation. In
production the sandbox is a :class:`~maistro.tools.sandbox.microvm.MicroVMSandbox`
(own kernel, default-deny network, capped mem/vCPU); tests inject a fake.

Layering (SPEC-208 §2): this provider owns *process isolation* — opencode runs
its own tools ``--auto`` entirely inside the VM, contained by the sandbox. The
turn's text result is returned as the response envelope; Warden (inbound) and the
``ActionGate`` (outbound, on anything maistro relays) are still applied by
``SafeHarnessRunner`` around this provider.

Wiring — point it at a repo::

    runner = opencode_microvm_runner(my_vmm_launcher, model="anthropic/claude-opus-4-8")
    registry.register(runner)
    registry.activate("harness_runner", "opencode")
    sid = await manager.start(agent_spec, workdir="/repos/my-project")  # the repo
"""

from __future__ import annotations

import base64
import shlex
from collections.abc import Sequence
from typing import Any

from maistro.capabilities.providers.subprocess_harness import (
    SandboxExec,
    SandboxFactory,
    SubprocessHarnessRunner,
    _message_text,
    _Session,
)
from maistro.tools.sandbox.microvm import (
    LauncherFn,
    MicroVMConfig,
    MicroVMSandbox,
    VMMLauncher,
)
from maistro.tools.sandbox.workspace import ensure_workspace

_OPENCODE_BINARY = "opencode"


class OpencodeHarnessRunner(SubprocessHarnessRunner):
    """Run each turn as ``opencode run`` inside a sandboxed checkout.

    ``model`` (``provider/model``) and ``agent`` map to opencode's ``--model`` /
    ``--agent`` flags; ``--auto`` auto-approves opencode's in-VM tool use so the
    turn is non-interactive. Cross-turn conversation continuity (``--continue`` /
    ``--session``) is a v1 enhancement — v0 relies on the repo filesystem as the
    shared state across turns, which is what a coding harness actually mutates.
    """

    def __init__(
        self,
        *,
        sandbox_factory: SandboxFactory,
        model: str | None = None,
        agent: str | None = None,
        extra_args: Sequence[str] = (),
        timeout: int = 300,
        trust_tier: str = "t2",
    ) -> None:
        super().__init__(
            name="opencode",
            # base ``command`` template is unused — build_command is overridden —
            # but the parent requires one; keep it representative.
            command="opencode run {prompt}",
            sandbox_factory=sandbox_factory,
            binary=_OPENCODE_BINARY,
            timeout=timeout,
            trust_tier=trust_tier,
        )
        self._model = model
        self._agent = agent
        self._extra_args = tuple(extra_args)

    def build_command(self, session: _Session, messages: list[dict[str, Any]]) -> str:
        """Render a non-interactive ``opencode run`` invocation for one turn.

        The prompt is transported base64-encoded and decoded at execution time,
        so the sandbox's dangerous-command filter (``is_dangerous_command``)
        scans only the *executable* portion of the command — prompt text that
        merely *mentions* something like ``rm -rf /`` (e.g. "add a regression
        test for rm -rf handling") is data, not shell, and must not trip the
        filter. The decoded text lands in an argv position, never evaluated.
        """
        prompt = "\n".join(_message_text(m) for m in messages if m.get("role") != "system")
        encoded = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
        parts = ["opencode", "run", "--auto"]
        if self._model:
            parts += ["--model", shlex.quote(self._model)]
        if self._agent:
            parts += ["--agent", shlex.quote(self._agent)]
        parts += [shlex.quote(a) for a in self._extra_args]
        parts.append(f'"$(printf %s {encoded} | base64 -d)"')
        return " ".join(parts)


def opencode_microvm_factory(
    launcher: VMMLauncher | LauncherFn,
    *,
    config: MicroVMConfig | None = None,
    env: dict[str, str] | None = None,
) -> SandboxFactory:
    """A ``SandboxFactory`` that boots a :class:`MicroVMSandbox` at each workdir.

    The ``workdir`` passed to ``start_session`` becomes the VM's workspace — i.e.
    the repo you point opencode at. Because that value is caller-controlled when
    this factory sits behind the harness-session API, it is validated against
    the same workspace allowlist the Docker sandbox path enforces
    (``ensure_workspace``) before any VM is constructed — a request for ``/``,
    ``/etc``, or any other non-allowlisted host path is rejected with
    ``ValueError``. ``launcher`` is the VMM seam (real in prod, fake in tests);
    ``env`` carries opencode's provider credentials into the VM.
    """
    shared_env = dict(env or {})

    async def factory(workdir: str) -> SandboxExec:
        workspace = str(ensure_workspace(workdir))
        return MicroVMSandbox(launcher, config=config, workspace=workspace, env=shared_env)

    return factory


def opencode_microvm_runner(
    launcher: VMMLauncher | LauncherFn,
    *,
    model: str | None = None,
    agent: str | None = None,
    config: MicroVMConfig | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> OpencodeHarnessRunner:
    """Convenience: an :class:`OpencodeHarnessRunner` backed by a microVM sandbox."""
    return OpencodeHarnessRunner(
        sandbox_factory=opencode_microvm_factory(launcher, config=config, env=env),
        model=model,
        agent=agent,
        timeout=timeout,
    )


__all__ = [
    "OpencodeHarnessRunner",
    "opencode_microvm_factory",
    "opencode_microvm_runner",
]
