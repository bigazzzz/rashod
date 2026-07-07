from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.db import get_db
from app.metrics import expenses_added_total
from app.rate_limit import limiter
from app.routes.events import _get_event_or_404, render_event_page
from app.schemas import ExpenseCreate

router = APIRouter()


@router.post("/e/{slug}/expenses")
@limiter.limit("30/minute")
def create_expense(
    request: Request,
    slug: str,
    payer_name: str = Form(...),
    description: str = Form(""),
    amount: str = Form(...),
    db: Session = Depends(get_db),
):
    event = _get_event_or_404(db, slug)

    error = None
    try:
        parsed_amount = Decimal(amount.replace(",", "."))
        data = ExpenseCreate(payer_name=payer_name, description=description, amount=parsed_amount)
    except (InvalidOperation, ValidationError) as exc:
        error = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else "Некорректная сумма"

    if error:
        return render_event_page(request, db, event, error=error, status_code=400)

    crud.add_expense(db, event, data.payer_name, data.description, data.amount)
    expenses_added_total.inc()
    return RedirectResponse(url=f"/e/{event.slug}", status_code=303)


@router.post("/e/{slug}/expenses/{expense_id}/delete")
@limiter.limit("30/minute")
def delete_expense(request: Request, slug: str, expense_id: int, db: Session = Depends(get_db)):
    event = _get_event_or_404(db, slug)
    crud.delete_expense(db, event, expense_id)
    return RedirectResponse(url=f"/e/{event.slug}", status_code=303)
