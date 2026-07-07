import os
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.db import get_db
from app.metrics import events_created_total
from app.rate_limit import limiter
from app.schemas import EventCreate
from app.settlement import compute_balances, compute_totals, settle_debts
from app.templating import templates

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
    }
    if error:
        context["error"] = error
    return templates.TemplateResponse(request, "event.html", context, status_code=status_code)


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.post("/events")
@limiter.limit("10/minute")
def create_event(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    try:
        data = EventCreate(name=name)
    except ValidationError as exc:
        error = exc.errors()[0]["msg"]
        return templates.TemplateResponse(
            request, "index.html", {"error": error}, status_code=400
        )

    event = crud.create_event(db, data.name)
    events_created_total.inc()
    return RedirectResponse(url=f"/e/{event.slug}", status_code=303)


@router.get("/e/{slug}")
def event_page(request: Request, slug: str, db: Session = Depends(get_db)):
    event = _get_event_or_404(db, slug)
    return render_event_page(request, db, event)


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
