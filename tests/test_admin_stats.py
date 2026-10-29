import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.admin_stats import (
    event_creation_series,
    top_events_by_expense_count,
    top_payment_descriptions,
)
from app.db import SessionLocal, init_db
from app.models import Event, Expense

init_db()


@pytest.fixture()
def db():
    session = SessionLocal()
    session.query(Expense).delete()
    session.query(Event).delete()
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _add_event(db, name: str, *, created_at: datetime | None = None) -> Event:
    event = Event(name=name, slug=secrets.token_hex(9))
    if created_at is not None:
        event.created_at = created_at
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _add_expense(db, event: Event, description: str, amount: str = "10.00") -> None:
    db.add(
        Expense(
            event_id=event.id,
            payer_name="A",
            description=description,
            amount=Decimal(amount),
        )
    )
    db.commit()


def test_top_events_by_expense_count_orders_and_limits(db):
    e1 = _add_event(db, "Few")
    e2 = _add_event(db, "Many")
    _add_event(db, "Empty")
    for _ in range(3):
        _add_expense(db, e2, "x")
    _add_expense(db, e1, "y")
    rows = top_events_by_expense_count(db, limit=2)
    assert len(rows) == 2
    assert rows[0]["slug"] == e2.slug
    assert rows[0]["expense_count"] == 3
    assert rows[1]["slug"] == e1.slug
    assert rows[1]["expense_count"] == 1


def test_top_payment_descriptions_normalizes_and_skips_empty(db):
    event = _add_event(db, "Desc")
    _add_expense(db, event, "Пицца")
    _add_expense(db, event, " пицца ")
    _add_expense(db, event, "Такси")
    _add_expense(db, event, "   ")
    rows = top_payment_descriptions(db, limit=10)
    assert rows[0]["count"] == 2
    assert rows[0]["description"].strip().casefold() == "пицца"
    assert all(r["description"].strip() for r in rows)
    assert len(rows) == 2


def test_event_creation_series_fills_zeros_and_weeks(db):
    now = datetime.now(timezone.utc)
    _add_event(db, "Today", created_at=now)
    _add_event(db, "Yesterday", created_at=now - timedelta(days=1))
    series = event_creation_series(db, days=7)
    assert series["granularity"] == "day"
    assert len(series["bucket_labels"]) == 7
    assert series["total"] == 2
    assert series["bucket_counts"][-1] >= 1
    assert series["bucket_counts"][-2] >= 1

    year = event_creation_series(db, days=365)
    assert year["granularity"] == "week"
    assert len(year["bucket_labels"]) >= 52
    assert year["total"] == 2
