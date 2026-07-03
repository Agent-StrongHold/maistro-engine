"""End-to-end driver for the ``harness_runner`` slot (SPEC-208).

``HarnessSessionManager`` is the glue between the capability slot, the safety
wrapper, and the sequence policy engine — the piece both the outbound graph node
and the inbound ``/v1/harness/sessions`` route build on:

- resolves the active ``harness_runner`` provider from the ``CapabilityRegistry``
  (respecting enable/health/fallback);
- wraps it in :class:`SafeHarnessRunner` — Warden scans every inbound message, and
  when a :class:`SequencePolicyEngine` is supplied a per-session
  :class:`PolicyActionGate` gates every outbound action (cumulative/sequence
  budgets across the whole session);
- when the slot is absent, disabled, or unhealthy it degrades to a typed
  ``Unavailable`` (SAFE_NOOP) — it never raises for a missing harness.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from maistro.agents.spec.agent_spec import AgentSpec
from maistro.capabilities.providers.harness_safety import ActionGate, SafeHarnessRunner
from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.slots.harness_runner import SLOT_NAME, HarnessRunner
from maistro.capabilities.types import Unavailable
from maistro.policy.engine import SequencePolicyEngine
from maistro.policy.gate import PolicyActionGate
from maistro.security.warden.detector import Warden


class HarnessSessionManager:
    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        warden: Warden,
        policy: SequencePolicyEngine | None = None,
    ) -> None:
        self._registry = registry
        self._warden = warden
        self._policy = policy
        self._sessions: dict[str, SafeHarnessRunner] = {}

    async def start(self, agent_spec: AgentSpec, *, workdir: str) -> str | Unavailable:
        """Resolve + start a safety-wrapped harness session, or ``Unavailable``."""
        provider = await self._registry.resolve(SLOT_NAME)
        if not isinstance(provider, HarnessRunner):
            return Unavailable(slot=SLOT_NAME, reason="no active harness_runner provider")
        session_id = await provider.start_session(agent_spec, workdir=workdir)
        gate: ActionGate | None = (
            PolicyActionGate(self._policy, key=session_id) if self._policy is not None else None
        )
        self._sessions[session_id] = SafeHarnessRunner(provider, warden=self._warden, gate=gate)
        return session_id

    async def send(
        self, session_id: str, messages: list[dict[str, Any]]
    ) -> dict[str, Any] | Unavailable:
        safe = self._sessions.get(session_id)
        if safe is None:
            return Unavailable(slot=SLOT_NAME, reason=f"unknown harness session: {session_id}")
        return await safe.send(session_id, messages)

    async def stream(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        safe = self._sessions.get(session_id)
        if safe is None:
            return
        async for event in safe.stream(session_id):
            yield event

    async def stop(self, session_id: str) -> None:
        safe = self._sessions.pop(session_id, None)
        if safe is not None:
            await safe.stop(session_id)

    def active_sessions(self) -> list[str]:
        return list(self._sessions)
