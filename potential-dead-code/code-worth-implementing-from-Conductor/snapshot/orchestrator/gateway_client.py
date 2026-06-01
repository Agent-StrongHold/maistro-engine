"""HTTP client for the Inference Gateway.

Includes retry logic with exponential backoff for transient failures.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 0.5
RETRYABLE_STATUS_CODES = {502, 503, 504}


@dataclass
class GatewayCompletion:
    content: str
    usage: dict


class GatewayError(Exception):
    """Raised when gateway communication fails after retries."""

    pass


class GatewayClient:
    """Async client for the Conductor Inference Gateway.

    Features:
    - Automatic retry with exponential backoff for transient errors
    - Safe response parsing with proper error handling
    - Configurable timeout (default: 10 minutes for long generations)
    """

    def __init__(
        self,
        base_url: str,
        max_retries: int = MAX_RETRIES,
        timeout_seconds: int = 600,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)
        self._max_retries = max_retries

    async def close(self) -> None:
        await self._client.aclose()

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """Make an HTTP request with retry logic."""
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                if method == "GET":
                    resp = await self._client.get(url, **kwargs)
                else:
                    resp = await self._client.post(url, **kwargs)

                if resp.status_code in RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "Retryable status %d on attempt %d for %s",
                        resp.status_code,
                        attempt + 1,
                        path,
                    )
                    last_error = httpx.HTTPStatusError(
                        f"Status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                else:
                    resp.raise_for_status()
                    return resp

            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                logger.warning("Transient error on attempt %d for %s: %s", attempt + 1, path, e)
                last_error = e

            # Exponential backoff
            if attempt < self._max_retries - 1:
                backoff = INITIAL_BACKOFF_SECONDS * (2**attempt)
                await asyncio.sleep(backoff)

        raise GatewayError(
            f"Request to {path} failed after {self._max_retries} attempts: {last_error}"
        )

    async def health(self) -> dict:
        resp = await self._request_with_retry("GET", "/health", timeout=5)
        return resp.json()

    async def chat(self, messages: list[dict], **kwargs) -> GatewayCompletion:
        """Single completion via /v1/chat/completions."""
        payload = {"messages": messages, **kwargs}
        resp = await self._request_with_retry("POST", "/v1/chat/completions", json=payload)
        data = resp.json()

        # Safe extraction with defaults
        try:
            choices = data.get("choices", [])
            if not choices:
                raise GatewayError("Empty choices in response")
            content = choices[0].get("message", {}).get("content", "")
        except (KeyError, IndexError, TypeError) as e:
            raise GatewayError(f"Malformed response from gateway: {e}")

        return GatewayCompletion(
            content=content,
            usage=data.get("usage", {}),
        )

    async def ultra_think(
        self,
        task_id: str,
        messages: list[dict],
        project_id: str,
        tier: int = 2,
        max_tokens: int | None = None,
        n_candidates: int | None = None,
    ) -> dict:
        """Parallel diverse generation via /v1/ultra-think."""
        payload = {
            "task_id": task_id,
            "messages": messages,
            "project_id": project_id,
            "tier": tier,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if n_candidates:
            payload["n_candidates"] = n_candidates

        resp = await self._request_with_retry("POST", "/v1/ultra-think", json=payload)
        return resp.json()

    async def load_project(
        self, project_id: str, layer0_text: str, knowledge_context: str = ""
    ) -> dict:
        """Load project context into template slot."""
        resp = await self._request_with_retry(
            "POST",
            "/v1/project/load",
            json={
                "project_id": project_id,
                "layer0_text": layer0_text,
                "knowledge_context": knowledge_context,
            },
        )
        return resp.json()
