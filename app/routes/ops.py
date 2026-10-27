"""Read-only internal ops endpoints for the MCP server (token-gated)."""

from __future__ import annotations

import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from prometheus_client import REGISTRY
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import __version__, crud
from app.cleanup import RETENTION_DAYS
from app.db import get_db
from app.metrics import (
    events_created_total,
    events_deleted_total,
    expenses_added_total,
)
from app.models import Event, Expense
from app.og_image import OG_IMAGE_DIR, background_path_for
from app.routes.events import PUBLIC_BASE_URL

router = APIRouter(prefix="/internal/ops", tags=["ops"], include_in_schema=False)

OPS_TOKEN = (os.environ.get("OPS_TOKEN") or "").strip()

_APP_COUNTERS = (
    events_created_total,
    expenses_added_total,
    events_deleted_total,
)


def require_ops_token(
    x_ops_token: Annotated[str | None, Header(alias="X-Ops-Token")] = None,
) -> None:
    if not OPS_TOKEN:
        raise HTTPException(status_code=404, detail="Not Found")
    if not x_ops_token or x_ops_token != OPS_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/health", dependencies=[Depends(require_ops_token)])
def ops_health(db: Session = Depends(get_db)):
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001 — report as unhealthy
        db_ok = False

    pollinations_configured = bool((os.environ.get("POLLINATIONS_API_KEY") or "").strip())
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "db_ok": db_ok,
        "og_dir_exists": OG_IMAGE_DIR.is_dir(),
        "pollinations_configured": pollinations_configured,
        "retention_days": RETENTION_DAYS,
        "public_base_url_set": bool(PUBLIC_BASE_URL),
    }


def _counter_value(counter) -> float:
    total = 0.0
    expected = f"{counter._name}_total"
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name == expected:
                total += float(sample.value)
    return total


@router.get("/stats", dependencies=[Depends(require_ops_token)])
def ops_stats(db: Session = Depends(get_db)):
    events = db.query(func.count(Event.id)).scalar() or 0
    expenses = db.query(func.count(Expense.id)).scalar() or 0
    # Not real accounts — free-text payer_name on expenses (counts only, no name list).
    unique_participants = (
        db.query(func.count(func.distinct(Expense.payer_name))).scalar() or 0
    )
    og_files = 0
    if OG_IMAGE_DIR.is_dir():
        og_files = sum(
            1
            for path in OG_IMAGE_DIR.glob("*.jpg")
            if path.is_file() and not path.name.startswith(".")
        )

    counters = {f"{c._name}_total": _counter_value(c) for c in _APP_COUNTERS}
    return {
        "events": int(events),
        "expenses": int(expenses),
        "og_files": og_files,
        "unique_participants": {
            "distinct_payer_names": int(unique_participants),
            "meaning": (
                "Count of distinct expense payer_name values. "
                "Not login accounts; same person may use different spellings."
            ),
        },
        "counters": counters,
    }


@router.get("/metrics/summary", dependencies=[Depends(require_ops_token)])
def ops_metrics_summary():
    """Compact Prometheus registry snapshot (capped)."""
    samples: list[dict] = []
    limit = 80
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if len(samples) >= limit:
                break
            # Skip high-cardinality python GC noise somewhat
            if sample.name.startswith("python_gc_"):
                continue
            samples.append(
                {
                    "name": sample.name,
                    "labels": dict(sample.labels),
                    "value": float(sample.value),
                }
            )
        if len(samples) >= limit:
            break
    return {"samples": samples, "truncated": len(samples) >= limit}


@router.get("/event/{slug}", dependencies=[Depends(require_ops_token)])
def ops_event_info(slug: str, request: Request, db: Session = Depends(get_db)):
    if not slug or len(slug) > 32 or any(c not in "0123456789abcdef" for c in slug):
        raise HTTPException(status_code=404, detail="Событие не найдено")

    event = crud.get_event_by_slug(db, slug)
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    expense_count = (
        db.query(func.count(Expense.id)).filter(Expense.event_id == event.id).scalar() or 0
    )
    base = PUBLIC_BASE_URL.rstrip("/") if PUBLIC_BASE_URL else str(request.base_url).rstrip("/")
    return {
        "slug": event.slug,
        "name": event.name,
        "created_at": event.created_at.isoformat(),
        "expense_count": int(expense_count),
        "has_og_background": background_path_for(event.slug) is not None,
        "urls": {
            "event": f"{base}/e/{event.slug}",
            "results": f"{base}/r/{event.slug}",
            "og": f"{base}/og/{event.slug}.jpg",
        },
    }


@router.get("/public-checks", dependencies=[Depends(require_ops_token)])
def ops_public_checks(request: Request):
    """Hit key public routes in-process — works in tests and in the web container."""
    from starlette.testclient import TestClient

    base = str(request.base_url).rstrip("/")
    paths = ("/healthz", "/", "/og/site.jpg")
    checks = []
    # Nested TestClient is fine for read-only smoke checks (no lifespan restart).
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
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            checks.append(
                {
                    "path": path,
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                    "error": error,
                    "via": "asgi",
                    "public_base": base,
                }
            )
    return {"checks": checks}
