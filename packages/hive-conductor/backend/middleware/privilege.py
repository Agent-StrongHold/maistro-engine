from __future__ import annotations

import fnmatch
import logging

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("hive.privilege_middleware")

_ADMIN_PATHS: frozenset[str] = frozenset()
_ADMIN_PREFIXES = ("/v1/settings",)


class PrivilegeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        return await call_next(request)
