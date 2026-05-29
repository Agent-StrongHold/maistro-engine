"""Context builder: assembles prompt from soul + tools + learnings + episodic.

Order matters: soul -> tool prompts -> promoted learnings -> matched learnings -> episodic memories.
Token budget enforcement prevents context overflow -- learnings are dropped (lowest priority first)
before soul prompt, which is never truncated.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maistro.protocols.memory import LearningStore
    from maistro.protocols.prompts import PromptManager
    from maistro.types.agent import AgentIdentity

logger = logging.getLogger("maistro.context_builder")

_LEARNINGS_BOUNDARY = "<maistro:corrections"

_CHARS_PER_TOKEN = 4

_DEFAULT_SYSTEM_TOKEN_BUDGET = 4096


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _render_learnings_block(
    learnings: list[Any],
    *,
    block_type: str,
    budget_chars: int,
    use_rca_prefix: bool,
) -> tuple[str | None, list[int], int]:
    """Render a ``<maistro:corrections>`` block within ``budget_chars``.

    Returns ``(block_text_or_None, kept_ids, added_count)``. ``block_text`` is
    ``None`` when nothing fit within the budget.
    """
    header = f'<maistro:corrections type="{block_type}">'
    footer = "</maistro:corrections>"
    overhead = len(header) + len(footer) + 2
    lines: list[str] = [header]
    used = overhead
    kept_ids: list[int] = []
    added = 0
    for lr in learnings:
        prefix = f"[{lr.rca_category}] " if use_rca_prefix and lr.rca_category else ""
        entry = f"- {prefix}{lr.learning}"
        if used + len(entry) + 1 > budget_chars:
            break
        lines.append(entry)
        used += len(entry) + 1
        added += 1
        if lr.id is not None:
            kept_ids.append(lr.id)
    if added == 0:
        return None, [], 0
    lines.append(footer)
    return "\n".join(lines), kept_ids, added


class ContextBuilder:
    """Assembles the full prompt context for an agent."""

    async def build(
        self,
        messages: list[dict[str, Any]],
        identity: AgentIdentity,
        *,
        prompt_manager: PromptManager,
        learning_store: LearningStore | None = None,
        agent_id: str = "",
        user_id: str = "",
        org_id: str = "",
        team_id: str = "",
        system_token_budget: int = _DEFAULT_SYSTEM_TOKEN_BUDGET,
        enable_cache_breakpoints: bool = False,
    ) -> tuple[list[dict[str, Any]], list[int]]:
        system_parts: list[str] = []
        budget_chars = system_token_budget * _CHARS_PER_TOKEN
        kept_ids: list[int] = []

        soul_name = identity.soul_prompt_name or f"agent.{identity.name}.soul"
        soul = await prompt_manager.get(soul_name)
        if soul:
            system_parts.append(soul)
            budget_chars -= len(soul)
            if budget_chars < 0:
                logger.warning(
                    "Soul prompt exceeds token budget: soul=%d chars, budget=%d tokens. "
                    "Learnings will be dropped.",
                    len(soul),
                    system_token_budget,
                )

        if learning_store and identity.memory_config.get("learnings") and budget_chars > 0:
            promoted = await learning_store.get_promoted(org_id=org_id)
            budget_chars = _apply_learnings(
                promoted,
                kind="promoted",
                use_rca_prefix=True,
                budget_chars=budget_chars,
                system_parts=system_parts,
                kept_ids=kept_ids,
            )

        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = str(msg.get("content", ""))
                break

        if (
            learning_store
            and user_text
            and identity.memory_config.get("learnings")
            and budget_chars > 0
        ):
            relevant = await learning_store.find_relevant(
                user_text,
                agent_id=agent_id,
                org_id=org_id,
            )
            budget_chars = _apply_learnings(
                relevant,
                kind="matched",
                use_rca_prefix=False,
                budget_chars=budget_chars,
                system_parts=system_parts,
                kept_ids=kept_ids,
            )

        result_messages = _assemble_messages(
            messages, system_parts, enable_cache_breakpoints=enable_cache_breakpoints
        )
        return result_messages, kept_ids


def _apply_learnings(
    learnings: list[Any],
    *,
    kind: str,
    use_rca_prefix: bool,
    budget_chars: int,
    system_parts: list[str],
    kept_ids: list[int],
) -> int:
    """Render a learnings block, append it to ``system_parts``, record its kept
    ids, and return the remaining ``budget_chars``."""
    if not learnings:
        return budget_chars
    block, block_ids, added = _render_learnings_block(
        learnings,
        block_type=kind,
        budget_chars=budget_chars,
        use_rca_prefix=use_rca_prefix,
    )
    if block is not None:
        system_parts.append(block)
        budget_chars -= len(block)
        kept_ids.extend(block_ids)
    if added < len(learnings):
        logger.debug(
            "Token budget: dropped %d/%d %s learnings",
            len(learnings) - added,
            len(learnings),
            kind,
        )
    return budget_chars


def _assemble_messages(
    messages: list[dict[str, Any]],
    system_parts: list[str],
    *,
    enable_cache_breakpoints: bool,
) -> list[dict[str, Any]]:
    """Prepend the assembled system context to ``messages`` (merging into an
    existing system message if present) and optionally inject cache breakpoints."""
    assembled = "\n\n".join(system_parts)
    result_messages = list(messages)

    if assembled:
        if result_messages and result_messages[0].get("role") == "system":
            result_messages[0] = {
                "role": "system",
                "content": assembled + "\n\n" + result_messages[0]["content"],
            }
        else:
            result_messages.insert(0, {"role": "system", "content": assembled})

    if enable_cache_breakpoints:
        result_messages = inject_cache_breakpoints(result_messages)

    return result_messages


def inject_cache_breakpoints(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = list(messages)
    if not result or result[0].get("role") != "system":
        return result

    system_msg = dict(result[0])
    content = system_msg["content"]

    if isinstance(content, str):
        idx = content.find(_LEARNINGS_BOUNDARY)
        if idx > 0:
            stable = content[:idx].rstrip()
            dynamic = content[idx:]
            blocks: list[dict[str, Any]] = [
                {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic},
            ]
        else:
            blocks = [
                {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}},
            ]
        system_msg["content"] = blocks
    elif isinstance(content, list):
        blocks = []
        for i, block in enumerate(content):
            new_block = dict(block)
            if i == 0 and "cache_control" not in new_block:
                new_block["cache_control"] = {"type": "ephemeral"}
            blocks.append(new_block)
        system_msg["content"] = blocks

    result[0] = system_msg
    return result
