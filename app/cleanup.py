import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from app import crud
from app.db import SessionLocal
from app.metrics import events_deleted_total

log = logging.getLogger("cleanup")

CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60  # daily is plenty for a day-granularity retention window


def parse_retention_days(raw: str) -> int:
    try:
        days = int(raw)
    except ValueError:
        raise ValueError(f"EVENT_RETENTION_DAYS must be an integer (got {raw!r})") from None
    if days <= 0:
        raise ValueError(f"EVENT_RETENTION_DAYS must be positive (got {days})")
    return days


RETENTION_DAYS = parse_retention_days(os.environ.get("EVENT_RETENTION_DAYS", "365"))


def cleanup_old_events() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    db = SessionLocal()
    try:
        deleted = crud.delete_events_older_than(db, cutoff)
        if deleted:
            events_deleted_total.inc(deleted)
            log.info("Cleaned up %d event(s) older than %d days", deleted, RETENTION_DAYS)
        return deleted
    finally:
        db.close()


async def run_cleanup_loop() -> None:
    while True:
        cleanup_old_events()
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
