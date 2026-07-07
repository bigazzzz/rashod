import secrets
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Event, Expense


def generate_unique_slug(db: Session) -> str:
    while True:
        slug = secrets.token_urlsafe(9)
        if db.query(Event).filter(Event.slug == slug).first() is None:
            return slug


def create_event(db: Session, name: str) -> Event:
    event = Event(name=name, slug=generate_unique_slug(db))
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_event_by_slug(db: Session, slug: str) -> Event | None:
    return db.query(Event).filter(Event.slug == slug).first()


def add_expense(
    db: Session, event: Event, payer_name: str, description: str, amount: Decimal
) -> Expense:
    expense = Expense(
        event_id=event.id,
        payer_name=payer_name.strip(),
        description=description.strip(),
        amount=amount,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def get_expenses(db: Session, event: Event) -> list[Expense]:
    return (
        db.query(Expense)
        .filter(Expense.event_id == event.id)
        .order_by(Expense.created_at)
        .all()
    )


def delete_expense(db: Session, event: Event, expense_id: int) -> bool:
    """Delete an expense if it belongs to the given event. Returns whether it was found."""
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.event_id == event.id)
        .first()
    )
    if expense is None:
        return False
    db.delete(expense)
    db.commit()
    return True


def delete_events_older_than(db: Session, cutoff: datetime) -> int:
    """Delete events created before `cutoff` (expenses go with them via
    cascade). Returns how many events were deleted."""
    old_events = db.query(Event).filter(Event.created_at < cutoff).all()
    for event in old_events:
        db.delete(event)
    db.commit()
    return len(old_events)
