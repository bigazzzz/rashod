import asyncio
import contextlib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # must run before app.db / app.routes.* read env vars at import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler as default_http_exception_handler
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.cleanup import run_cleanup_loop
from app.db import init_db
from app.rate_limit import limiter
from app.routes import events, expenses
from app.templating import templates

STATIC_DIR = Path(__file__).parent / "static"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    cleanup_task = asyncio.create_task(run_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(title="Поровну", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


# #region agent log
@app.middleware("http")
async def _agent_log_all_requests(request: Request, call_next):
    import time as _t
    from fastapi.responses import JSONResponse as _J
    from app.debug_og import agent_log, recent_hits
    if request.url.path == "/debug/og-hits":
        if request.query_params.get("token") != "0784a2":
            raise HTTPException(status_code=404)
        return _J({"hits": recent_hits()})
    t0 = _t.perf_counter()
    response = await call_next(request)
    if not request.url.path.startswith(("/static", "/metrics", "/healthz")):
        h = request.headers
        agent_log(hypothesis_id="ABC", location="main.py:middleware", message="request", data={"method": request.method, "path": request.url.path, "status": response.status_code, "ms": int((_t.perf_counter() - t0) * 1000), "resp_len": response.headers.get("content-length"), "resp_type": response.headers.get("content-type"), "ua": h.get("user-agent", "")[:120], "accept": h.get("accept", "")[:80], "range": h.get("range"), "ip": h.get("x-forwarded-for")})
    return response
# #endregion
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(events.router)
app.include_router(expenses.router)

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request, "404.html", {"detail": exc.detail}, status_code=404
        )
    return await default_http_exception_handler(request, exc)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return templates.TemplateResponse(
        request, "429.html", {}, status_code=429
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    # Do not Disallow /e/: VK/Telegram/etc. need to fetch event pages for Open Graph.
    # Privacy for search engines is handled via noindex on event templates.
    return PlainTextResponse("User-agent: *\nAllow: /\n")
