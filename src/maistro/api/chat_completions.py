"""OpenAI-compatible /v1/chat/completions endpoint for Open WebUI integration.

This translates between OpenAI chat format and the Maistro conductor pipeline.
Supports streaming SSE responses.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from maistro.api.auth import RequireAuth

router = APIRouter(prefix="/v1", tags=["openai-compat"])


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "maistro-tier-2"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:8]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)


class DeltaMessage(BaseModel):
    role: str | None = None
    content: str | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str = ""
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[StreamChoice]


async def _stream_conductor_response(
    request: ChatCompletionRequest,
) -> AsyncIterator[str]:
    """Stream the conductor response as SSE chunks."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

    # Send role chunk
    role_chunk = ChatCompletionChunk(
        id=chunk_id,
        model=request.model,
        choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
    )
    yield f"data: {role_chunk.model_dump_json()}\n\n"

    # For Phase 1, run the conductor and stream the final_answer in chunks.
    # Phase 2 will stream real-time progress from sub-agents.
    from maistro.agents.conductor import run_task
    from maistro.tasks.models import TaskCreate

    user_msg = next(
        (m.content for m in reversed(request.messages) if m.role == "user" and m.content),
        "",
    )

    task = TaskCreate(description=user_msg or "No task specified")
    try:
        result = await run_task(task)
        response_text = result.final_answer or "Task completed successfully."
    except Exception:
        import structlog
        await structlog.get_logger().aexception("chat_completion_stream_error")
        response_text = "An internal error occurred while processing your request."

    # Stream content in small chunks for responsive feel
    chunk_size = 20
    for i in range(0, len(response_text), chunk_size):
        text_chunk = response_text[i : i + chunk_size]
        content_chunk = ChatCompletionChunk(
            id=chunk_id,
            model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(content=text_chunk))],
        )
        yield f"data: {content_chunk.model_dump_json()}\n\n"

    # Send finish chunk
    finish_chunk = ChatCompletionChunk(
        id=chunk_id,
        model=request.model,
        choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
    )
    yield f"data: {finish_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    _auth: RequireAuth,
) -> ChatCompletionResponse | StreamingResponse:
    if request.stream:
        return StreamingResponse(
            _stream_conductor_response(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming: run conductor and return full response
    from maistro.agents.conductor import run_task
    from maistro.tasks.models import TaskCreate

    user_msg = next(
        (m.content for m in reversed(request.messages) if m.role == "user" and m.content),
        "",
    )

    task = TaskCreate(description=user_msg or "No task specified")
    try:
        result = await run_task(task)
        response_text = result.final_answer or "Task completed successfully."
    except Exception:
        import structlog
        await structlog.get_logger().aexception("chat_completion_error")
        response_text = "An internal error occurred while processing your request."

    return ChatCompletionResponse(
        model=request.model,
        choices=[
            Choice(message=ChatMessage(role="assistant", content=response_text)),
        ],
    )
