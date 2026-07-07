from datetime import datetime, timedelta, timezone

import pytest

from app import crud
from app.cleanup import parse_retention_days
from app.db import SessionLocal


def _create_event_with_age(client, name: str, age_days: int) -> str:
    response = client.post("/events", data={"name": name}, follow_redirects=False)
    slug = response.headers["location"].split("/e/")[1]

    db = SessionLocal()
    try:
        event = crud.get_event_by_slug(db, slug)
        event.created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
        db.commit()
    finally:
        db.close()
    return slug


def test_delete_events_older_than_removes_only_old_events(client):
    old_slug = _create_event_with_age(client, "Старое", age_days=400)
    new_slug = _create_event_with_age(client, "Новое", age_days=10)

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        deleted = crud.delete_events_older_than(db, cutoff)
    finally:
        db.close()

    assert deleted == 1
    assert client.get(f"/e/{old_slug}").status_code == 404
    assert client.get(f"/e/{new_slug}").status_code == 200


def test_delete_events_older_than_cascades_to_expenses(client):
    slug = _create_event_with_age(client, "С тратами", age_days=400)
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "amount": "10"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        from app.models import Expense

        assert db.query(Expense).count() == 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        deleted = crud.delete_events_older_than(db, cutoff)
        assert deleted == 1
        assert db.query(Expense).count() == 0
    finally:
        db.close()


def test_parse_retention_days_accepts_positive_int():
    assert parse_retention_days("365") == 365
    assert parse_retention_days("1") == 1


def test_parse_retention_days_rejects_non_integer():
    with pytest.raises(ValueError, match="must be an integer"):
        parse_retention_days("soon")


def test_parse_retention_days_rejects_zero_or_negative():
    with pytest.raises(ValueError, match="must be positive"):
        parse_retention_days("0")
    with pytest.raises(ValueError, match="must be positive"):
        parse_retention_days("-5")
