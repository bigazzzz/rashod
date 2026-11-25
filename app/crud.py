import logging
import re
import secrets
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.models import Event, Expense

log = logging.getLogger(__name__)


def generate_unique_slug(db: Session) -> str:
    while True:
        slug = secrets.token_hex(9)
        if db.query(Event).filter(Event.slug == slug).first() is None:
            return slug


def create_event(db: Session, name: str) -> Event:
    event = Event(name=name, slug=generate_unique_slug(db))
    db.add(event)
    db.commit()
    db.refresh(event)
    log.info("event_created")
    return event


def get_event_by_slug(db: Session, slug: str) -> Event | None:
    return db.query(Event).filter(Event.slug == slug).first()


def add_expense(
    db: Session, event: Event, payer_name: str, description: str, amount: Decimal
) -> Expense:
    """Store a payment, allocating blank payer names within the write transaction."""
    payer_name = payer_name.strip()
    if not payer_name:
        # A write locks this event (the database on SQLite) until commit.
        # Both the lookup and the insert must run under that same lock.
        db.execute(update(Event).where(Event.id == event.id).values(name=Event.name))
        names = db.query(Expense.payer_name).filter(Expense.event_id == event.id).distinct()
        highest = 0
        for (name,) in names:
            match = re.fullmatch(r"user(\d+)", name.casefold())
            if match:
                highest = max(highest, int(match[1]))
        payer_name = f"User{highest + 1:03d}"

    expense = Expense(
        event_id=event.id,
        payer_name=payer_name,
        description=description.strip(),
        amount=amount,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    log.info("expense_added")
    return expense


def get_expenses(db: Session, event: Event) -> list[Expense]:
    return (
        db.query(Expense)
        .filter(Expense.event_id == event.id)
        .order_by(Expense.created_at, Expense.id)
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
    log.info("expense_deleted")
    return True


def delete_event(db: Session, event: Event) -> None:
    """Delete a single event (expenses cascade)."""
    db.delete(event)
    db.commit()


def delete_events_older_than(db: Session, cutoff: datetime) -> int:
    """Delete events created before `cutoff` (expenses go with them via
    cascade). Returns how many events were deleted."""
    old_events = db.query(Event).filter(Event.created_at < cutoff).all()
    for event in old_events:
        db.delete(event)
    db.commit()
    return len(old_events)


def list_events(
    db: Session,
    *,
    q: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[tuple[Event, int]], int]:
    """Return (event, expense_count) rows plus total matching count."""
    filters = []
    if q:
        needle = f"%{q.strip()}%"
        filters.append((Event.name.ilike(needle)) | (Event.slug.ilike(needle)))

    total_q = db.query(func.count(Event.id))
    for f in filters:
        total_q = total_q.filter(f)
    total = int(total_q.scalar() or 0)

    expense_count = func.count(Expense.id).label("expense_count")
    query = (
        db.query(Event, expense_count)
        .outerjoin(Expense, Expense.event_id == Event.id)
        .group_by(Event.id)
    )
    for f in filters:
        query = query.filter(f)
    rows = (
        query.order_by(Event.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [(event, int(count or 0)) for event, count in rows], total
