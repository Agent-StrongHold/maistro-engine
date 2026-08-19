"""Policy enforcement and causal audit events around canonical capability Invocations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from maistro.capabilities.binding import Binding
from maistro.capabilities.invocation import (
    Invocation,
    InvocationExecutionService,
    InvocationStatus,
    ProviderExecutor,
    ProviderResolver,
)
from maistro.events.envelope import EventEnvelope, EventStore
from maistro.policy.types import Decision, PolicyVerdict


@dataclass(frozen=True)
class InvocationPolicyContext:
    """Canonical execution identity available to capability policy evaluation."""

    run_id: str
    node_run_id: str
    attempt_id: str
    effect_key: str


PolicyEvaluator = Callable[[Binding, Any, InvocationPolicyContext], Awaitable[PolicyVerdict]]


class InvocationDenied(PermissionError):
    """Policy explicitly denied a capability Invocation."""


class InvocationApprovalRequired(PermissionError):
    """Policy requires human approval before an Invocation may proceed."""


class GovernedInvocationExecutionService:
    """Apply policy once, record the decision, then cross the Invocation boundary.

    This wrapper deliberately delegates physical provider-call lifecycle and
    idempotency to :class:`InvocationExecutionService`; it does not create a
    second Invocation state machine.
    """

    def __init__(
        self,
        *,
        invocation_service: InvocationExecutionService,
        event_store: EventStore,
        policy_evaluator: PolicyEvaluator,
    ) -> None:
        self._invocations = invocation_service
        self._events = event_store
        self._policy = policy_evaluator

    async def latest_effect(
        self,
        *,
        binding: Binding,
        run_id: str,
        node_run_id: str,
        effect_key: str,
    ) -> Invocation | None:
        """Expose canonical effect history without bypassing governed execution."""

        return await self._invocations.latest_effect(
            binding=binding,
            run_id=run_id,
            node_run_id=node_run_id,
            effect_key=effect_key,
        )

    async def invoke(
        self,
        *,
        binding: Binding,
        run_id: str,
        node_run_id: str,
        attempt_id: str,
        effect_key: str,
        request: Any,
        resolver: ProviderResolver,
        executor: ProviderExecutor,
    ) -> Invocation:
        context = InvocationPolicyContext(
            run_id=run_id,
            node_run_id=node_run_id,
            attempt_id=attempt_id,
            effect_key=effect_key,
        )
        verdict = await self._policy(binding, request, context)
        policy_event = await self._events.append(
            EventEnvelope(
                type="capability.invocation.policy_decision",
                workspace_id=binding.workspace_id,
                project_id=binding.project_id,
                run_id=run_id,
                node_run_id=node_run_id,
                attempt_id=attempt_id,
                correlation_id=run_id,
                source="maistro.capabilities",
                payload={
                    "binding_id": binding.binding_id,
                    "capability": binding.capability,
                    "effect_key": effect_key,
                    "decision": verdict.decision.value,
                    "reason": verdict.reason,
                    "rule": verdict.rule,
                },
            )
        )

        if verdict.decision is Decision.DENY:
            raise InvocationDenied(verdict.reason or "capability invocation denied by policy")
        if verdict.decision is Decision.REQUIRE_APPROVAL:
            raise InvocationApprovalRequired(
                verdict.reason or "capability invocation requires approval"
            )

        try:
            invocation = await self._invocations.invoke(
                binding=binding,
                run_id=run_id,
                node_run_id=node_run_id,
                attempt_id=attempt_id,
                effect_key=effect_key,
                request=request,
                resolver=resolver,
                executor=executor,
            )
        except asyncio.CancelledError:
            await self._append_latest_terminal_event(
                binding=binding,
                run_id=run_id,
                node_run_id=node_run_id,
                effect_key=effect_key,
                causation_id=policy_event.event_id,
            )
            raise
        except Exception:
            await self._append_latest_terminal_event(
                binding=binding,
                run_id=run_id,
                node_run_id=node_run_id,
                effect_key=effect_key,
                causation_id=policy_event.event_id,
            )
            raise

        await self._append_terminal_event(
            invocation,
            binding=binding,
            causation_id=policy_event.event_id,
        )
        return invocation

    async def _append_latest_terminal_event(
        self,
        *,
        binding: Binding,
        run_id: str,
        node_run_id: str,
        effect_key: str,
        causation_id: str,
    ) -> None:
        invocation = await self.latest_effect(
            binding=binding,
            run_id=run_id,
            node_run_id=node_run_id,
            effect_key=effect_key,
        )
        if invocation is None or invocation.status not in {
            InvocationStatus.COMPLETED,
            InvocationStatus.FAILED,
            InvocationStatus.UNKNOWN,
        }:
            return
        await self._append_terminal_event(
            invocation,
            binding=binding,
            causation_id=causation_id,
        )

    async def _append_terminal_event(
        self,
        invocation: Invocation,
        *,
        binding: Binding,
        causation_id: str,
    ) -> None:
        """Append one idempotent terminal audit fact for a persisted Invocation."""

        await self._events.append(
            EventEnvelope(
                event_id=(
                    f"capability-invocation-{invocation.invocation_id}-{invocation.status.value}"
                ),
                type=f"capability.invocation.{invocation.status.value}",
                workspace_id=binding.workspace_id,
                project_id=binding.project_id,
                run_id=invocation.run_id,
                node_run_id=invocation.node_run_id,
                attempt_id=invocation.attempt_id,
                invocation_id=invocation.invocation_id,
                correlation_id=invocation.run_id,
                causation_id=causation_id,
                source="maistro.capabilities",
                payload={
                    "binding_id": invocation.binding.binding_id,
                    "capability": invocation.binding.capability,
                    "effect_key": invocation.effect_key,
                    "provider_name": invocation.binding.provider_name,
                    "status": invocation.status.value,
                    "error": invocation.error,
                },
            )
        )


__all__ = [
    "GovernedInvocationExecutionService",
    "InvocationApprovalRequired",
    "InvocationDenied",
    "InvocationPolicyContext",
    "PolicyEvaluator",
]
