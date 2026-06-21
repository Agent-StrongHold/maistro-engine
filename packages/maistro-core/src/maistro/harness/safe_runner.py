"""Safety wrapper for HarnessRunner providers.

The wrapper is intentionally provider-agnostic: every message is scanned by
Warden before the wrapped harness sees it, and every returned action/tool call is
checked before it is surfaced to maistro.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from maistro.capabilities.protocols import HarnessRunner
from maistro.capabilities.types import ProviderHealth
from maistro.security.warden.detector import Warden
from maistro.types.config import AgentConfig

ActionChecker = Callable[[dict[str, Any]], Awaitable[bool]]


class HarnessSecurityError(RuntimeError):
    """Raised when Warden or Sentinel-style action policy blocks a harness turn."""


async def allow_all_actions(action: dict[str, Any]) -> bool:
    """Default action checker for harnesses without tool execution enabled."""

    return True


@dataclass
class SafeHarnessRunner:
    """Compose Warden ingress scanning and Sentinel-style action gating around a runner."""

    inner: HarnessRunner
    warden: Warden
    action_checker: ActionChecker = allow_all_actions

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def slot(self) -> str:
        return self.inner.slot

    @property
    def trust_tier(self) -> str:
        return self.inner.trust_tier

    def requires(self) -> tuple[str, ...]:
        return self.inner.requires()

    async def healthcheck(self) -> ProviderHealth:
        return await self.inner.healthcheck()

    async def start_session(self, agent_spec: AgentConfig, *, workdir: str) -> str:
        return await self.inner.start_session(agent_spec, workdir=workdir)

    async def send(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        await self._scan_messages(messages)
        response = await self.inner.send(session_id, messages)
        await self._check_actions(response)
        return response

    async def stream(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        async for event in self.inner.stream(session_id):
            await self._check_actions(event)
            yield event

    async def stop(self, session_id: str) -> None:
        await self.inner.stop(session_id)

    async def _scan_messages(self, messages: list[dict[str, Any]]) -> None:
        for idx, message in enumerate(messages):
            content = message.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, sort_keys=True)
            verdict = await self.warden.scan(content, "user_input")
            if not verdict.clean or verdict.blocked:
                flags = ", ".join(verdict.flags) or "unknown"
                raise HarnessSecurityError(f"Warden blocked harness message {idx}: {flags}")

    async def _check_actions(self, envelope: dict[str, Any]) -> None:
        actions = _extract_actions(envelope)
        for action in actions:
            allowed = await self.action_checker(action)
            if not allowed:
                name = action.get("name") or action.get("tool") or action.get("action") or "unknown"
                raise HarnessSecurityError(f"Sentinel blocked harness action: {name}")


def _extract_actions(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all action/tool-call dictionaries from common harness envelopes."""

    raw_actions: list[Any] = []
    for key in ("actions", "tool_calls", "toolCalls"):
        value = envelope.get(key)
        if isinstance(value, list):
            raw_actions.extend(value)
    message = envelope.get("message")
    if isinstance(message, dict):
        value = message.get("tool_calls") or message.get("toolCalls")
        if isinstance(value, list):
            raw_actions.extend(value)
    return [action for action in raw_actions if isinstance(action, dict)]
