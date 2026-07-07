from prometheus_client import Counter

events_created_total = Counter("events_created_total", "Number of events created")
expenses_added_total = Counter("expenses_added_total", "Number of expenses added")
events_deleted_total = Counter(
    "events_deleted_total", "Number of events deleted by the retention cleanup job"
)
