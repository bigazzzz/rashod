from pathlib import Path
from shutil import disk_usage

from prometheus_client import Counter, Gauge

from app.db import engine

events_created_total = Counter("events_created_total", "Number of events created")
expenses_added_total = Counter("expenses_added_total", "Number of expenses added")
events_deleted_total = Counter(
    "events_deleted_total", "Number of events deleted by the retention cleanup job"
)


def _storage_free_ratio(directory: Path) -> float:
    try:
        usage = disk_usage(directory)
    except OSError:
        return float("nan")
    return usage.free / usage.total if usage.total else float("nan")


if engine.url.get_backend_name() == "sqlite" and engine.url.database not in (None, "", ":memory:"):
    database_directory = Path(engine.url.database).absolute().parent
    Gauge(
        "porovnu_sqlite_storage_free_ratio",
        "Fraction of space available on the filesystem containing the SQLite database",
    ).set_function(lambda: _storage_free_ratio(database_directory))
