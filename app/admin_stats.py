"""Read-only aggregates for the admin dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models import Event, Expense

TOP_LIMIT = 20
CHART_PERIODS = (7, 30, 90, 365)
DEFAULT_CHART_DAYS = 30


def top_events_by_expense_count(db: Session, *, limit: int = TOP_LIMIT) -> list[dict]:
    expense_count = func.count(Expense.id).label("expense_count")
    rows = (
        db.query(
            Event.id,
            Event.name,
            Event.slug,
            Event.created_at,
            expense_count,
        )
        .outerjoin(Expense, Expense.event_id == Event.id)
        .group_by(Event.id)
        .order_by(desc(expense_count), desc(Event.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "rank": index,
            "name": row.name,
            "slug": row.slug,
            "expense_count": int(row.expense_count or 0),
            "created_at": row.created_at,
        }
        for index, row in enumerate(rows, start=1)
    ]


def top_payment_descriptions(db: Session, *, limit: int = TOP_LIMIT) -> list[dict]:
    """Group by casefold(trim(description)); SQLite lower() is ASCII-only."""
    from collections import Counter, defaultdict

    rows = db.query(Expense.description).all()
    counts: Counter[str] = Counter()
    samples: dict[str, Counter[str]] = defaultdict(Counter)
    for (raw,) in rows:
        text = (raw or "").strip()
        if not text:
            continue
        key = text.casefold()
        counts[key] += 1
        samples[key][text] += 1

    result: list[dict] = []
    for index, (key, cnt) in enumerate(counts.most_common(limit), start=1):
        label = samples[key].most_common(1)[0][0]
        result.append({"rank": index, "description": label, "count": int(cnt)})
    return result


def event_creation_series(db: Session, *, days: int = DEFAULT_CHART_DAYS) -> dict:
    """Bucket counts of Event.created_at over the last `days` (inclusive of today)."""
    if days not in CHART_PERIODS:
        days = DEFAULT_CHART_DAYS

    now = datetime.now(timezone.utc)
    end_day = now.date()
    start_day = end_day - timedelta(days=days - 1)
    start_dt = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)

    day_expr = func.date(Event.created_at)
    raw = (
        db.query(day_expr.label("day"), func.count().label("cnt"))
        .filter(Event.created_at >= start_dt)
        .group_by(day_expr)
        .all()
    )
    by_day: dict[date, int] = {}
    for row in raw:
        if row.day is None:
            continue
        if isinstance(row.day, date) and not isinstance(row.day, datetime):
            key = row.day
        else:
            key = date.fromisoformat(str(row.day)[:10])
        by_day[key] = int(row.cnt)

    use_weeks = days == 365
    labels: list[str] = []
    values: list[int] = []

    if use_weeks:
        cursor = start_day - timedelta(days=start_day.weekday())
        while cursor <= end_day:
            week_end = cursor + timedelta(days=6)
            total = 0
            day = cursor
            while day <= week_end:
                if start_day <= day <= end_day:
                    total += by_day.get(day, 0)
                day += timedelta(days=1)
            labels.append(cursor.isoformat())
            values.append(total)
            cursor += timedelta(days=7)
        granularity = "week"
    else:
        day = start_day
        while day <= end_day:
            labels.append(day.isoformat())
            values.append(by_day.get(day, 0))
            day += timedelta(days=1)
        granularity = "day"

    return {
        "days": days,
        "granularity": granularity,
        # Avoid key name "values" — Jinja treats chart.values as dict.values().
        "bucket_labels": labels,
        "bucket_counts": values,
        "total": sum(values),
    }
