from __future__ import annotations

from typing import Any, Protocol

from models.schemas import ChatCompletionRequest


class LLMPort(Protocol):
    async def complete(self, req: ChatCompletionRequest) -> dict[str, Any]: ...
