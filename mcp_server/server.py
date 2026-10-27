"""Porovnu ops MCP server — read-only tools over /internal/ops."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.auth import BearerAuthMiddleware, RateLimitMiddleware
from mcp_server.client import OpsClientError, ops_get

load_dotenv()

log = logging.getLogger("porovnu.mcp")
logging.basicConfig(
    level=os.environ.get("MCP_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_SLUG_RE = re.compile(r"^[0-9a-f]{18}$")

mcp = FastMCP(
    name="porovnu-ops",
    instructions=(
        "Read-only operations for porovnu.su: health, stats, metrics, "
        "event metadata, and public URL checks. No writes, no PII from expenses."
    ),
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8080")),
    streamable_http_path="/mcp",
    stateless_http=True,
)


def _audit(tool: str, started: float, *, ok: bool, detail: str = "") -> None:
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    log.info(
        "tool=%s ok=%s latency_ms=%s %s",
        tool,
        ok,
        latency_ms,
        detail,
    )


def _tool_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tool_error(message: str) -> str:
    return _tool_result({"error": message})


@mcp.tool(description="Application health: version, DB, OG dir, config flags (no secrets).")
def health() -> str:
    started = time.perf_counter()
    try:
        data = ops_get("/internal/ops/health")
        _audit("health", started, ok=True)
        return _tool_result(data)
    except OpsClientError as exc:
        _audit("health", started, ok=False, detail=str(exc))
        return _tool_error(str(exc))


@mcp.tool(description="Site stats: event/expense/OG counts and app Prometheus counters.")
def site_stats() -> str:
    started = time.perf_counter()
    try:
        data = ops_get("/internal/ops/stats")
        _audit("site_stats", started, ok=True)
        return _tool_result(data)
    except OpsClientError as exc:
        _audit("site_stats", started, ok=False, detail=str(exc))
        return _tool_error(str(exc))


@mcp.tool(description="Compact Prometheus metrics summary (capped sample list).")
def metrics_summary() -> str:
    started = time.perf_counter()
    try:
        data = ops_get("/internal/ops/metrics/summary")
        _audit("metrics_summary", started, ok=True)
        return _tool_result(data)
    except OpsClientError as exc:
        _audit("metrics_summary", started, ok=False, detail=str(exc))
        return _tool_error(str(exc))


@mcp.tool(
    description=(
        "Event metadata by hex slug (name, dates, expense_count, OG flag, public URLs). "
        "Does not include payer names, amounts, or expense descriptions."
    )
)
def event_info(slug: str) -> str:
    started = time.perf_counter()
    slug = (slug or "").strip()
    if not _SLUG_RE.match(slug):
        _audit("event_info", started, ok=False, detail="invalid_slug")
        return _tool_error("Invalid slug: expected 18 hex characters")
    try:
        data = ops_get(f"/internal/ops/event/{slug}")
        _audit("event_info", started, ok=True)
        return _tool_result(data)
    except OpsClientError as exc:
        _audit("event_info", started, ok=False, detail=str(exc))
        return _tool_error(str(exc))


@mcp.tool(description="Smoke-check public routes: /healthz, /, /og/site.jpg (status + latency).")
def public_checks() -> str:
    started = time.perf_counter()
    try:
        data = ops_get("/internal/ops/public-checks")
        _audit("public_checks", started, ok=True)
        return _tool_result(data)
    except OpsClientError as exc:
        _audit("public_checks", started, ok=False, detail=str(exc))
        return _tool_error(str(exc))


def create_http_app():
    """Starlette app with Bearer auth + rate limit around streamable HTTP."""
    app = mcp.streamable_http_app()
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BearerAuthMiddleware)
    return app


def main() -> None:
    import uvicorn

    app = create_http_app()
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    log.info("Starting porovnu MCP on %s:%s path=/mcp", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
