"""Per-IP rate limiting for the public MCP HTTP transport."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

RATE_LIMIT_PER_MINUTE = int(os.environ.get("MCP_RATE_LIMIT_PER_MINUTE") or "60")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limit: int = RATE_LIMIT_PER_MINUTE):
        super().__init__(app)
        self.limit = max(1, limit)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        key = self._client_key(request)
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.limit:
            return JSONResponse({"error": "Rate limit exceeded"}, status_code=429)
        window.append(now)
        return await call_next(request)
