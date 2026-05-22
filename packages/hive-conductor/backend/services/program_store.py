"""Per-user program context persistence for PM hyperagent."""

from __future__ import annotations

import logging
from typing import Any

from maistro.agents.program_context import ProgramContext

logger = logging.getLogger("hive.program")


def get_context(user_id: str) -> ProgramContext:
    import stores

    raw = stores.program_contexts.get(user_id)
    if raw is None:
        ctx = ProgramContext.empty(user_id)
        stores.program_contexts[user_id] = ctx.model_dump(mode="json")
        return ctx
    return ProgramContext.model_validate(raw)


def save_context(ctx: ProgramContext) -> ProgramContext:
    import stores

    stores.program_contexts[ctx.user_id] = ctx.model_dump(mode="json")
    logger.debug("program_context_saved user=%s step=%s", ctx.user_id, ctx.interview_step)
    return ctx


def context_dict(user_id: str) -> dict[str, Any]:
    return get_context(user_id).model_dump(mode="json")
