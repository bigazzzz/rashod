import time

import httpx
from fastapi import Request


async def public_checks(request: Request) -> list[dict]:
    """Probe the running ASGI app without starting another application lifespan."""
    base = str(request.base_url).rstrip("/")
    transport = httpx.ASGITransport(app=request.app, raise_app_exceptions=False)
    checks = []
    async with httpx.AsyncClient(transport=transport, base_url=base) as client:
        for path in ("/healthz", "/", "/og/site.jpg"):
            started = time.perf_counter()
            status_code = None
            error = None
            try:
                response = await client.get(path)
                status_code = response.status_code
            except httpx.HTTPError as exc:
                error = type(exc).__name__
            checks.append({
                "path": path,
                "status_code": status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": error,
                "via": "asgi",
                "public_base": base,
            })
    return checks
