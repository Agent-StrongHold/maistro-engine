from __future__ import annotations

from typing import Any, Protocol

from models.schemas import ChatCompletionRequest


class LLMPort(Protocol):
    """Any model gateway that can turn a chat-style request into a JSON completion payload."""

    async def complete(self, req: ChatCompletionRequest) -> dict[str, Any]:
        """Return a JSON object shaped like OpenAI chat.completions (stable for the UI)."""
        ...
