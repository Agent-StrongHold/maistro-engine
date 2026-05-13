"""Token bucket rate limiter middleware.

Per-client rate limiting using a simple in-memory token bucket.
Returns HTTP 429 with Retry-After header when exceeded.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from maistro.config.settings import get_settings
from maistro.observability.metrics import http_request_duration, http_requests_total


class _TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate  # tokens per second
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client rate limiting via token bucket."""

    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._buckets: dict[str, _TokenBucket] = {}

    def _get_bucket(self, client_ip: str) -> _TokenBucket:
        if client_ip not in self._buckets:
            settings = get_settings()
            rate = settings.rate_limit_per_minute / 60.0
            self._buckets[client_ip] = _TokenBucket(rate=rate, burst=settings.rate_limit_burst)
        return self._buckets[client_ip]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for health endpoints
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket = self._get_bucket(client_ip)

        if not bucket.allow():
            settings = get_settings()
            retry_after = int(60 / settings.rate_limit_per_minute) + 1
            http_requests_total.inc(method=request.method, path=request.url.path, status="429")
            return JSONResponse(
                status_code=429,
                content={"error": {"type": "rate_limited", "message": "Too many requests"}},
                headers={"Retry-After": str(retry_after)},
            )

        t0 = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - t0

        http_requests_total.inc(
            method=request.method, path=request.url.path, status=str(response.status_code)
        )
        http_request_duration.observe(duration, method=request.method, path=request.url.path)
        return response
