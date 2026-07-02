"""Reference ``harness_runner`` provider: a CLI-style harness in a sandbox (SPEC-208 §1-2).

``SubprocessHarnessRunner`` runs each turn as a sandboxed subprocess. It is the
base that concrete foreign-harness adapters (``pi``, ``openclaw``, ``codex``)
specialize by overriding :meth:`build_command`. The sandbox is injected as a
seam (``SandboxExec``) so the provider is testable without a live container and
so the production wiring (``maistro.tools.sandbox``) — or a future microVM
backend (SPEC-190) — drops in without touching this class.

Safety wrapping (Warden inbound + Sentinel/ActionGate outbound) is applied by
``SafeHarnessRunner``; this class owns *process isolation* (every turn executes
inside the injected sandbox, never on the host).
"""

from __future__ import annotations

import shlex
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from maistro.agents.spec.agent_spec import AgentSpec
from maistro.capabilities.slots.harness_runner import SLOT_NAME
from maistro.capabilities.types import ProviderHealth


@runtime_checkable
class SandboxExec(Protocol):
    """Minimal process-isolation seam: run a command, return ``(exit_code, output)``.

    Matches ``maistro.tools.sandbox.docker.SandboxContainer.exec`` so the real
    sandbox satisfies it directly; tests inject an in-memory fake.
    """

    async def exec(self, command: str, timeout: int = 60) -> tuple[int, str]: ...


SandboxFactory = Callable[[str], Awaitable[SandboxExec]]


@dataclass
class _Session:
    agent_spec: AgentSpec
    workdir: str
    sandbox: SandboxExec


class SubprocessHarnessRunner:
    """Drive a CLI harness one turn per sandboxed subprocess.

    ``command`` is a template containing a ``{prompt}`` placeholder that is
    replaced with the shell-quoted, concatenated non-system messages. Concrete
    adapters override :meth:`build_command` for richer per-harness invocation.
    """

    def __init__(
        self,
        *,
        name: str,
        command: str,
        sandbox_factory: SandboxFactory,
        binary: str | None = None,
        timeout: int = 120,
        trust_tier: str = "t2",
    ) -> None:
        self._name = name
        self._command = command
        self._sandbox_factory = sandbox_factory
        self._binary = binary if binary is not None else name
        self._timeout = timeout
        self._trust_tier = trust_tier
        self._sessions: dict[str, _Session] = {}

    # --- CapabilityProvider ---
    @property
    def name(self) -> str:
        return self._name

    @property
    def slot(self) -> str:
        return SLOT_NAME

    @property
    def trust_tier(self) -> str:
        return self._trust_tier

    def requires(self) -> tuple[str, ...]:
        return (self._binary,)

    async def healthcheck(self) -> ProviderHealth:
        """Reflect both binary presence and sandbox reachability (SPEC-208 §2)."""
        try:
            sandbox = await self._sandbox_factory(".")
            code, output = await sandbox.exec(f"command -v {shlex.quote(self._binary)}", 10)
        except Exception as exc:
            return ProviderHealth(healthy=False, detail=f"sandbox unreachable: {exc}")
        if code != 0:
            return ProviderHealth(healthy=False, detail=f"binary not found: {self._binary}")
        return ProviderHealth(healthy=True, detail=output.strip())

    # --- HarnessRunner ---
    async def start_session(self, agent_spec: AgentSpec, *, workdir: str) -> str:
        session_id = uuid.uuid4().hex
        sandbox = await self._sandbox_factory(workdir)
        self._sessions[session_id] = _Session(
            agent_spec=agent_spec, workdir=workdir, sandbox=sandbox
        )
        return session_id

    def build_command(self, session: _Session, messages: list[dict[str, Any]]) -> str:
        """Render the harness invocation for a turn. Override per harness."""
        prompt = "\n".join(_message_text(m) for m in messages if m.get("role") != "system")
        return self._command.replace("{prompt}", shlex.quote(prompt))

    async def send(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        session = self._require_session(session_id)
        command = self.build_command(session, messages)
        code, output = await session.sandbox.exec(command, self._timeout)
        return {
            "role": "assistant",
            "content": output,
            "exit_code": code,
            "actions": [],
        }

    async def stream(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        # The reference subprocess adapter runs to completion (no incremental
        # tokens); concrete streaming harnesses override this. Yield a single
        # readiness event so the protocol is satisfied and callers can iterate.
        self._require_session(session_id)
        yield {"type": "status", "session_id": session_id, "state": "ready"}

    async def stop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    # --- internals ---
    def _require_session(self, session_id: str) -> _Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"unknown harness session: {session_id}")
        return session


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    return content if isinstance(content, str) else str(content)
