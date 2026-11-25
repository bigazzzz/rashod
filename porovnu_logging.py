"""Logging shared by the web and MCP services."""

import json
import logging
import os
import sys
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.config import dictConfig
from uuid import uuid4


LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
http_log = logging.getLogger("porovnu.http")


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "service": self.service,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if correlation_id := request_id.get():
            entry["request_id"] = correlation_id
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(service: str) -> None:
    default_level = os.environ.get("LOG_LEVEL", "INFO")
    raw_level = os.environ.get("MCP_LOG_LEVEL", default_level) if service == "mcp" else default_level
    level = raw_level.strip().upper() or "INFO"
    if level not in LEVELS:
        raise ValueError("LOG_LEVEL and MCP_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")

    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": JsonFormatter, "service": service}},
        "handlers": {"stdout": {
            "class": "logging.StreamHandler", "stream": sys.stdout, "formatter": "json", "level": level,
        }},
        "root": {"handlers": ["stdout"], "level": level},
        # Wire-level client debug logs can expose headers and request URLs.
        "loggers": {
            name: {"level": "WARNING", "handlers": [], "propagate": True}
            for name in ("httpx", "httpcore", "mcp", "sse_starlette")
        },
    })


class RequestLoggingMiddleware:
    def __init__(self, app, *, service_route: str | None = None) -> None:
        self.app = app
        self.service_route = service_route

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        correlation_id = uuid4().hex
        token = request_id.set(correlation_id)
        status = 500
        error_type = None

        async def send_with_request_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {
                    **message,
                    "headers": [*message.get("headers", []), (b"x-request-id", correlation_id.encode("ascii"))],
                }
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            try:
                self._log_request(scope, status, started, error_type)
            finally:
                request_id.reset(token)

    def _log_request(self, scope, status: int, started: float, error_type: str | None) -> None:
        route = getattr(scope.get("route"), "path", None)
        if route is None and scope.get("path") == self.service_route:
            route = self.service_route
        if error_type or status >= 500:
            level = logging.ERROR
        elif status >= 400:
            level = logging.WARNING
        elif route in ("/healthz", "/metrics", None):
            level = logging.DEBUG
        else:
            level = logging.INFO
        fields = {
            "method": scope["method"],
            "route": route or "unmatched",
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        if error_type:
            fields["error_type"] = error_type
        http_log.log(level, "http_request", extra={"fields": fields})
