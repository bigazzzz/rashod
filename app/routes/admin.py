"""Browser admin UI — session cookie auth, not OPS_TOKEN."""

from __future__ import annotations

import logging
import os
import secrets
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import __version__, crud
from app.admin_stats import (
    CHART_PERIODS,
    DEFAULT_CHART_DAYS,
    event_creation_series,
    top_events_by_expense_count,
    top_payment_descriptions,
)
from app.cleanup import RETENTION_DAYS, cleanup_old_events
from app.db import get_db
from app.metrics import (
    events_created_total,
    events_deleted_total,
    expenses_added_total,
)
from app.models import Event, Expense
from app.og_image import OG_IMAGE_DIR, background_path_for, delete_background_for
from app.rate_limit import limiter
from app.routes.events import PUBLIC_BASE_URL
from app.templating import templates

log = logging.getLogger("admin")

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)

ADMIN_PASSWORD = (os.environ.get("ADMIN_PASSWORD") or "").strip()
ADMIN_SESSION_SECRET = (os.environ.get("ADMIN_SESSION_SECRET") or "").strip()

_SESSION_FLAG = "admin_ok"
_CSRF_KEY = "admin_csrf"
_APP_COUNTERS = (
    events_created_total,
    expenses_added_total,
    events_deleted_total,
)

EVENTS_PAGE_SIZE = 50


def admin_configured() -> bool:
    return bool(ADMIN_PASSWORD and ADMIN_SESSION_SECRET)


def _require_configured() -> None:
    if not admin_configured():
        raise HTTPException(status_code=404, detail="Not Found")


def _is_logged_in(request: Request) -> bool:
    return bool(request.session.get(_SESSION_FLAG))


def _require_login(request: Request) -> RedirectResponse | None:
    """Return a login redirect if needed; otherwise None."""
    _require_configured()
    if not _is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    return None


def _ensure_csrf(request: Request) -> str:
    token = request.session.get(_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[_CSRF_KEY] = token
    return token


def _verify_csrf(request: Request, csrf_token: str | None) -> None:
    expected = request.session.get(_CSRF_KEY)
    if not expected or not csrf_token or not secrets.compare_digest(expected, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def _counter_value(counter) -> float:
    total = 0.0
    expected = f"{counter._name}_total"
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name == expected:
                total += float(sample.value)
    return total


def _base_url(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


def _flash_redirect(path: str, *, notice: str | None = None, error: str | None = None) -> RedirectResponse:
    params = {}
    if notice:
        params["notice"] = notice
    if error:
        params["error"] = error
    url = path if not params else f"{path}?{urlencode(params)}"
    return RedirectResponse(url, status_code=303)


@router.get("")
@router.get("/")
def admin_home(request: Request, db: Session = Depends(get_db), days: int = Query(DEFAULT_CHART_DAYS)):
    if redir := _require_login(request):
        return redir
    if days not in CHART_PERIODS:
        days = DEFAULT_CHART_DAYS

    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False

    events = db.query(func.count(Event.id)).scalar() or 0
    expenses = db.query(func.count(Expense.id)).scalar() or 0
    og_files = 0
    if OG_IMAGE_DIR.is_dir():
        og_files = sum(
            1
            for path in OG_IMAGE_DIR.glob("*.jpg")
            if path.is_file() and not path.name.startswith(".")
        )

    series = event_creation_series(db, days=days)
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "csrf_token": _ensure_csrf(request),
            "health": {
                "status": "ok" if db_ok else "degraded",
                "version": __version__,
                "db_ok": db_ok,
                "og_dir_exists": OG_IMAGE_DIR.is_dir(),
                "pollinations_configured": bool(
                    (os.environ.get("POLLINATIONS_API_KEY") or "").strip()
                ),
                "retention_days": RETENTION_DAYS,
                "public_base_url_set": bool(PUBLIC_BASE_URL),
            },
            "stats": {
                "events": int(events),
                "expenses": int(expenses),
                "og_files": int(og_files),
                "counters": {f"{c._name}_total": _counter_value(c) for c in _APP_COUNTERS},
            },
            "top_events": top_events_by_expense_count(db),
            "top_descriptions": top_payment_descriptions(db),
            "chart": series,
            "chart_periods": CHART_PERIODS,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/login")
def admin_login_page(request: Request):
    _require_configured()
    if _is_logged_in(request):
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {
            "csrf_token": _ensure_csrf(request),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/login")
@limiter.limit("10/minute")
def admin_login(
    request: Request,
    password: str = Form(""),
    csrf_token: str = Form(""),
):
    _require_configured()
    _verify_csrf(request, csrf_token)
    if secrets.compare_digest(password, ADMIN_PASSWORD):
        request.session[_SESSION_FLAG] = True
        _ensure_csrf(request)  # rotate
        request.session[_CSRF_KEY] = secrets.token_urlsafe(32)
        log.info("admin login success")
        return RedirectResponse("/admin/", status_code=303)
    log.warning("admin login failed")
    return _flash_redirect("/admin/login", error="Неверный пароль")


@router.post("/logout")
def admin_logout(
    request: Request,
    csrf_token: str = Form(""),
):
    _require_configured()
    _verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/events")
def admin_events_list(
    request: Request,
    db: Session = Depends(get_db),
    q: str = Query(""),
    page: int = Query(1, ge=1),
):
    if redir := _require_login(request):
        return redir
    offset = (page - 1) * EVENTS_PAGE_SIZE
    rows, total = crud.list_events(db, q=q or None, offset=offset, limit=EVENTS_PAGE_SIZE)
    pages = max(1, (total + EVENTS_PAGE_SIZE - 1) // EVENTS_PAGE_SIZE)
    return templates.TemplateResponse(
        request,
        "admin/events.html",
        {
            "csrf_token": _ensure_csrf(request),
            "rows": rows,
            "q": q,
            "page": page,
            "pages": pages,
            "total": total,
            "base_url": _base_url(request),
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/events/{slug}")
def admin_event_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    if redir := _require_login(request):
        return redir
    if not slug or len(slug) > 32 or any(c not in "0123456789abcdef" for c in slug):
        raise HTTPException(status_code=404, detail="Событие не найдено")
    event = crud.get_event_by_slug(db, slug)
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    expense_count = (
        db.query(func.count(Expense.id)).filter(Expense.event_id == event.id).scalar() or 0
    )
    base = _base_url(request)
    return templates.TemplateResponse(
        request,
        "admin/event_detail.html",
        {
            "csrf_token": _ensure_csrf(request),
            "event": event,
            "expense_count": int(expense_count),
            "has_og_background": background_path_for(event.slug) is not None,
            "urls": {
                "event": f"{base}/e/{event.slug}",
                "results": f"{base}/r/{event.slug}",
                "og": f"{base}/og/{event.slug}.jpg",
            },
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/events/{slug}/delete")
def admin_delete_event(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    csrf_token: str = Form(""),
):
    if redir := _require_login(request):
        return redir
    _verify_csrf(request, csrf_token)
    if not slug or len(slug) > 32 or any(c not in "0123456789abcdef" for c in slug):
        raise HTTPException(status_code=404, detail="Событие не найдено")
    event = crud.get_event_by_slug(db, slug)
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    crud.delete_event(db, event)
    delete_background_for(slug)
    events_deleted_total.inc()
    log.info("admin deleted event slug=%s", slug)
    return _flash_redirect("/admin/events", notice=f"Событие {slug} удалено")


@router.post("/cleanup")
def admin_run_cleanup(
    request: Request,
    csrf_token: str = Form(""),
):
    if redir := _require_login(request):
        return redir
    _verify_csrf(request, csrf_token)
    deleted = cleanup_old_events()
    return _flash_redirect(
        "/admin/",
        notice=f"Cleanup: удалено событий — {deleted} (retention {RETENTION_DAYS} дн.)",
    )


@router.get("/checks")
def admin_public_checks(request: Request):
    if redir := _require_login(request):
        return redir
    from starlette.testclient import TestClient

    paths = ("/healthz", "/", "/og/site.jpg")
    checks = []
    with TestClient(request.app, raise_server_exceptions=False) as client:
        for path in paths:
            started = time.perf_counter()
            status_code: int | None = None
            error: str | None = None
            try:
                resp = client.get(path)
                status_code = resp.status_code
            except Exception as exc:  # noqa: BLE001
                error = type(exc).__name__
            checks.append(
                {
                    "path": path,
                    "status_code": status_code,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    "error": error,
                }
            )
    return templates.TemplateResponse(
        request,
        "admin/checks.html",
        {
            "csrf_token": _ensure_csrf(request),
            "checks": checks,
        },
    )
