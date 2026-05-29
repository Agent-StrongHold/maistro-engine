"""Conduit — the request pipeline through which all requests flow.

Every request enters through the Conduit. It orchestrates:
1. Intent classification (what does the user want?)
2. Agent dispatch (route to the right specialist)
3. Response formatting (OpenAI-compatible output)

The Conduit never executes tasks directly — it decides and delegates.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from maistro.types.intent import Intent

if TYPE_CHECKING:
    from maistro.container import Container

logger = logging.getLogger("maistro.conduit")


async def determine_execution_tier(intent: Intent, agent: Any = None) -> Intent:
    """Apply agent priority_tier override if set."""
    import dataclasses

    current_tier = intent.tier
    if agent is not None and hasattr(agent, "priority_tier"):
        current_tier = agent.priority_tier
    if current_tier != intent.tier:
        return dataclasses.replace(intent, tier=current_tier)
    return intent


class Conduit:
    """Request pipeline: classify → route → agent.handle → response."""

    def __init__(self, container: Container) -> None:
        self.container = container

    async def route_request(
        self,
        messages: list[dict[str, Any]],
        *,
        auth: Any = None,
        session_id: str | None = None,
        intent_hint: str = "",
    ) -> dict[str, Any]:
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if not last_user_msg:
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "No message provided."},
                        "finish_reason": "stop",
                    }
                ],
            }

        # 1. Gate scan
        gate_result = await self.container.gate.process_input(last_user_msg, auth=auth)
        if gate_result.blocked:
            logger.warning("Gate blocked: %s", gate_result.block_reason)
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"Request blocked: {gate_result.block_reason}",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }

        # 2. Classify intent
        intent = await self.container.classifier.classify(
            messages,
            self.container.config.task_types,
        )
        if intent_hint:
            from maistro.types.intent import TIER_ORDER

            for task_type in TIER_ORDER:
                if task_type == intent_hint.upper():
                    import dataclasses

                    intent = dataclasses.replace(intent, task_type=task_type)
                    break

        logger.info(
            "Classified: task_type=%s complexity=%s tier=%s",
            intent.task_type,
            intent.complexity,
            intent.tier,
        )

        # 3. Resolve agent
        agent_name = self.container.intent_registry.resolve(intent.task_type)
        agent = self.container.agents.get(agent_name)

        if agent is None:
            agent = next(iter(self.container.agents.values())) if self.container.agents else None

        if agent is None:
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "No agents available."},
                        "finish_reason": "stop",
                    }
                ],
            }

        # 4. Determine execution tier
        intent = await determine_execution_tier(intent, agent)

        # 5. Dispatch to agent
        try:
            result = await agent.handle(
                messages=messages,
                intent=intent,
                auth=auth,
                session_id=session_id,
            )
        except Exception as exc:
            logger.exception("Agent %s failed", agent_name)
            return {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": f"Agent error: {exc}"},
                        "finish_reason": "stop",
                    }
                ],
            }

        if isinstance(result, dict):
            return result

        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": str(result)},
                    "finish_reason": "stop",
                }
            ],
        }
