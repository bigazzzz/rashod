import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.cleanup import RETENTION_DAYS
from app.db import get_db
from app.debug_og import agent_log, recent_hits
from app.metrics import events_created_total
from app.og_image import render_event_og_jpeg
from app.rate_limit import limiter
from app.schemas import EventCreate
from app.settlement import compute_balances, compute_totals, settle_debts
from app.templating import templates
from app.versions import current_version, load_releases

router = APIRouter()

def _validate_public_base_url(value: str | None) -> str | None:
    value = value or None
    if value and not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError(
            f"PUBLIC_BASE_URL must start with http:// or https:// (got {value!r})"
        )
    return value


# Overrides the request-derived host when building shareable links — needed
# whenever the app is reached through a proxy/tunnel/custom domain that
# doesn't match what request.base_url would report (e.g. ngrok, a reverse
# proxy without forwarded-host, or just wanting a fixed public domain).
PUBLIC_BASE_URL = _validate_public_base_url(os.environ.get("PUBLIC_BASE_URL"))


def _get_event_or_404(db: Session, slug: str):
    event = crud.get_event_by_slug(db, slug)
    if event is None:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")
    return event


DESCRIPTION_CHIPS = (
    "продукты",
    "топливо",
    "такси",
    "жильё",
    "бар",
    "алкоголь",
    "кафе",
    "билеты",
    "аптека",
    "гид",
    "экскурсия",
    "концерт",
    "прочее",
)

AMOUNT_CHIPS = (
    "000",
    "300",
    "500",
    "1000",
    "1500",
    "2000",
    "3000",
    "4000",
    "5000",
)

_DEFAULT_DESCRIPTION_SET = frozenset(DESCRIPTION_CHIPS)


def _unique_payer_names(expenses) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for expense in expenses:
        name = expense.payer_name
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _frequent_descriptions(expenses, *, min_count: int = 2) -> list[str]:
    """Descriptions used at least min_count times in this event, excluding defaults."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for expense in expenses:
        text = (expense.description or "").strip()
        if not text:
            continue
        if text not in counts:
            counts[text] = 0
            order.append(text)
        counts[text] += 1

    repeated = [text for text in order if counts[text] >= min_count]
    repeated.sort(key=lambda text: (-counts[text], order.index(text)))
    return [text for text in repeated if text not in _DEFAULT_DESCRIPTION_SET]


def _event_expires_at(event) -> datetime:
    created = event.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created + timedelta(days=RETENTION_DAYS)


def render_event_page(
    request: Request,
    db: Session,
    event,
    error: str | None = None,
    status_code: int = 200,
):
    expenses = crud.get_expenses(db, event)
    total = sum((e.amount for e in expenses), Decimal("0"))
    base_url = PUBLIC_BASE_URL.rstrip("/") if PUBLIC_BASE_URL else str(request.base_url).rstrip("/")
    context = {
        "event": event,
        "expenses": expenses,
        "total": total,
        "share_url": f"{base_url}/e/{event.slug}",
        "og_image_url": f"{base_url}/og/{event.slug}.jpg",
        "known_names": _unique_payer_names(expenses),
        "amount_chips": AMOUNT_CHIPS,
        "description_chips": DESCRIPTION_CHIPS,
        "frequent_description_chips": _frequent_descriptions(expenses),
        "expires_at": _event_expires_at(event),
    }
    if error:
        context["error"] = error
    return templates.TemplateResponse(request, "event.html", context, status_code=status_code)


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_version": current_version(),
            "releases": load_releases(limit=3),
        },
    )


@router.post("/events")
@limiter.limit("10/minute")
def create_event(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    try:
        data = EventCreate(name=name)
    except ValidationError as exc:
        error = exc.errors()[0]["msg"]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "error": error,
                "app_version": current_version(),
                "releases": load_releases(limit=3),
            },
            status_code=400,
        )

    event = crud.create_event(db, data.name)
    events_created_total.inc()
    return RedirectResponse(url=f"/e/{event.slug}", status_code=303)


@router.get("/e/{slug}")
def event_page(request: Request, slug: str, db: Session = Depends(get_db)):
    t0 = time.perf_counter()
    event = _get_event_or_404(db, slug)
    response = render_event_page(request, db, event)
    # #region agent log
    ua = request.headers.get("user-agent", "")
    agent_log(
        hypothesis_id="A",
        location="events.py:event_page",
        message="event page served",
        data={
            "slug": slug,
            "method": request.method,
            "ua": ua[:180],
            "is_bot": any(
                token in ua.lower()
                for token in (
                    "telegrambot",
                    "vkshare",
                    "vkbot",
                    "facebookexternalhit",
                    "twitterbot",
                    "whatsapp",
                    "slackbot",
                    "linkedinbot",
                )
            ),
            "base_url_env": bool(PUBLIC_BASE_URL),
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        },
    )
    # #endregion
    return response


def _og_image_response(event, *, request: Request | None = None, route: str = "") -> Response:
    t0 = time.perf_counter()
    png = render_event_og_jpeg(event.name)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    # #region agent log
    ua = request.headers.get("user-agent", "") if request is not None else ""
    agent_log(
        hypothesis_id="C",
        location="events.py:og_image",
        message="og image rendered",
        data={
            "slug": event.slug,
            "route": route,
            "method": request.method if request is not None else "?",
            "ua": ua[:180],
            "bytes": len(png),
            "render_ms": elapsed_ms,
            "is_bot": any(
                token in ua.lower()
                for token in (
                    "telegrambot",
                    "vkshare",
                    "vkbot",
                    "facebookexternalhit",
                    "twitterbot",
                    "whatsapp",
                )
            ),
        },
    )
    # #endregion
    return Response(
        content=png,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(len(png)),
        },
    )


@router.api_route("/og/{slug}.jpg", methods=["GET", "HEAD"])
def event_og_image(request: Request, slug: str, db: Session = Depends(get_db)):
    # Outside /e/ so social crawlers are not blocked if robots ever restricts events again.
    event = _get_event_or_404(db, slug)
    return _og_image_response(event, request=request, route="/og/{slug}.jpg")


@router.api_route("/og/{slug}.png", methods=["GET", "HEAD"], include_in_schema=False)
def event_og_image_png_legacy(request: Request, slug: str, db: Session = Depends(get_db)):
    event = _get_event_or_404(db, slug)
    return _og_image_response(event, request=request, route="/og/{slug}.png")


@router.api_route("/e/{slug}/og.png", methods=["GET", "HEAD"], include_in_schema=False)
def event_og_image_legacy(request: Request, slug: str, db: Session = Depends(get_db)):
    event = _get_event_or_404(db, slug)
    return _og_image_response(event, request=request, route="/e/{slug}/og.png")


@router.get("/debug/og-hits", include_in_schema=False)
def debug_og_hits(request: Request):
    # Temporary debug endpoint; token keeps casual scanners out.
    if request.query_params.get("token") != "0784a2":
        raise HTTPException(status_code=404, detail="Not found")
    # #region agent log
    agent_log(
        hypothesis_id="D",
        location="events.py:debug_og_hits",
        message="hits dumped",
        data={"count": len(recent_hits())},
    )
    # #endregion
    return JSONResponse({"hits": recent_hits()})


@router.get("/e/{slug}/results")
def results_page(request: Request, slug: str, db: Session = Depends(get_db)):
    event = _get_event_or_404(db, slug)
    expenses = crud.get_expenses(db, event)

    totals = compute_totals([(e.payer_name, e.amount) for e in expenses])
    balances = compute_balances(totals)
    transfers = settle_debts(balances)

    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "event": event,
            "totals": totals,
            "transfers": transfers,
        },
    )
