import asyncio
import contextlib
import os
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
from starlette.middleware.sessions import SessionMiddleware

from app.cleanup import run_cleanup_loop
from app.db import init_db
from app.rate_limit import limiter
from app.routes import admin, events, expenses, ops
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
# Session cookie is only useful for /admin; placeholder secret keeps middleware
# importable when admin is disabled (routes still 404 without real credentials).
_session_secret = admin.ADMIN_SESSION_SECRET or "disabled-admin-sessions"
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    session_cookie="porovnu_admin",
    max_age=60 * 60 * 12,
    same_site="lax",
    https_only=os.environ.get("ADMIN_COOKIE_SECURE", "0") == "1",
    path="/admin",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(events.router)
app.include_router(expenses.router)
app.include_router(ops.router)
app.include_router(admin.router)

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
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /admin/\n"
    )