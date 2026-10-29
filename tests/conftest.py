import os
import tempfile

import pytest

_tmp_dir = tempfile.mkdtemp(prefix="split-expenses-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
# Pin every env var app.main's load_dotenv() could otherwise pick up from a
# developer's real, uncommitted .env (e.g. a PUBLIC_BASE_URL left uncommented
# for manual docker testing) so test behavior never depends on local machine
# state.
os.environ["PUBLIC_BASE_URL"] = ""
os.environ["EVENT_RETENTION_DAYS"] = "365"
os.environ["OG_IMAGE_DIR"] = os.path.join(_tmp_dir, "og")
os.environ["POLLINATIONS_API_KEY"] = ""
os.environ["OPS_TOKEN"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["ADMIN_SESSION_SECRET"] = ""
os.environ["ADMIN_COOKIE_SECURE"] = "0"
os.makedirs(os.environ["OG_IMAGE_DIR"], exist_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def disable_pollinations_network(monkeypatch):
    """Tests must not hit Pollinations; create_event schedules a background task."""
    monkeypatch.setattr(
        "app.routes.events.generate_and_store_background",
        lambda slug, name: None,
    )


@pytest.fixture()
def client():
    app.state.limiter.reset()
    with TestClient(app) as c:
        yield c
