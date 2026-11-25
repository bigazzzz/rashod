"""Public MCP for Поровну: create an event and add an expense."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.auth import RateLimitMiddleware
from mcp_server.client import OpsClientError, ops_post
from porovnu_logging import RequestLoggingMiddleware, configure_logging

load_dotenv()

log = logging.getLogger("porovnu.mcp")

_SLUG_RE = re.compile(r"^[0-9a-f]{18}$")

mcp = FastMCP(
    name="porovnu",
    instructions=(
        "Публичные действия на Поровну: создать событие и добавить в него трату. "
        "Чужие суммы и имена не показывать и не запрашивать. "
        "После создания события отдай человеку ссылки на страницу события и на расчёт."
    ),
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8080")),
    streamable_http_path="/mcp",
    stateless_http=True,
)


def _audit(tool: str, started: float, *, error: str | None = None, status: int | None = None) -> None:
    fields = {"tool": tool, "ok": error is None, "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
    level = logging.INFO
    if error:
        fields.update(error=error, upstream_status=status)
        level = logging.ERROR if error == "upstream" and (status is None or status >= 500) else logging.WARNING
    log.log(level, "mcp_tool", extra={"fields": fields})


def _tool_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tool_error(message: str) -> str:
    return _tool_result({"error": message})


@mcp.tool(
    description=(
        "Создать событие по названию. Пустое название — ошибка. "
        "В ответе slug и ссылки на страницу события и на расчёт."
    )
)
def create_event(name: str) -> str:
    started = time.perf_counter()
    try:
        data = ops_post("/internal/ops/events", {"name": name})
        _audit("create_event", started)
        return _tool_result(data)
    except OpsClientError as exc:
        _audit("create_event", started, error="upstream", status=exc.status_code)
        return _tool_error(str(exc))


@mcp.tool(
    description=(
        "Добавить трату в событие по slug (18 hex-символов). "
        "amount — сумма, запятая или точка; 0 допустим и тогда назначение очищается. "
        "payer_name можно не указывать — подставится User001, User002 и так далее. "
        "Отрицательная сумма — ошибка. В ответе только эта трата и ссылка на событие."
    )
)
def add_expense(
    slug: str,
    amount: str = "0",
    description: str = "",
    payer_name: str = "",
) -> str:
    started = time.perf_counter()
    slug = (slug or "").strip()
    if not _SLUG_RE.match(slug):
        _audit("add_expense", started, error="invalid_slug")
        return _tool_error("Неверный slug: нужны 18 шестнадцатеричных символов")
    try:
        data = ops_post(
            f"/internal/ops/events/{slug}/expenses",
            {
                "amount": amount,
                "description": description,
                "payer_name": payer_name,
            },
        )
        _audit("add_expense", started)
        return _tool_result(data)
    except OpsClientError as exc:
        _audit("add_expense", started, error="upstream", status=exc.status_code)
        return _tool_error(str(exc))


def create_http_app():
    """Starlette app with a per-IP rate limit around streamable HTTP. No bearer auth."""
    app = mcp.streamable_http_app()
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware, service_route="/mcp")
    return app


def main() -> None:
    import uvicorn

    configure_logging("mcp")
    app = create_http_app()
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    log.info("Starting porovnu MCP on %s:%s path=/mcp", host, port)
    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
