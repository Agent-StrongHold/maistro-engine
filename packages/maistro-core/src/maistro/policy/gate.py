"""Bridge the policy engine to the harness ``ActionGate`` shape (SPEC-208 tie-in).

``PolicyActionGate`` satisfies the ``ActionGate`` protocol used by
``SafeHarnessRunner`` *structurally* — it exposes ``async def allow(action)`` and
imports nothing from the capabilities layer, so the policy package stays
lower-level and dependency-light. It maps a harness action dict onto a policy
:class:`Action` and charges it against the engine; only ALLOW permits the action.
"""

from __future__ import annotations

from typing import Any

from maistro.policy.engine import SequencePolicyEngine
from maistro.policy.types import Action


def _as_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class PolicyActionGate:
    def __init__(
        self,
        engine: SequencePolicyEngine,
        *,
        key: str,
        kind_field: str = "tool",
    ) -> None:
        self._engine = engine
        self._key = key
        self._kind_field = kind_field

    async def allow(self, action: dict[str, Any]) -> bool:
        act = Action(
            kind=str(action.get(self._kind_field, "unknown")),
            tokens=int(_as_number(action.get("tokens", 0))),
            cost=_as_number(action.get("cost", 0)),
            seconds=_as_number(action.get("seconds", 0)),
            metadata=action,
        )
        return self._engine.charge(self._key, act).allowed
