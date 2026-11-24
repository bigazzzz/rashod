import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import unquote

import httpx
import pytest

from PIL import Image

from app.og_image import (
    OG_IMAGE_DIR,
    WIDTH,
    HEIGHT,
    background_path_for,
    delete_background_for,
    render_event_og_jpeg,
    save_generated_background,
)
from app.pollinations import fetch_cartoon_background


def _tiny_jpeg_bytes(color=(40, 80, 120)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.parametrize("key", ["", "test-key"])
def test_fetch_sends_full_russian_prompt(monkeypatch, key):
    monkeypatch.setenv("POLLINATIONS_API_KEY", key)
    title = "Пикник у Маши / на Волге?"
    payload = _tiny_jpeg_bytes()

    def respond(request):
        if key:
            assert request.url.host == "gen.pollinations.ai"
            assert request.headers["Authorization"] == f"Bearer {key}"
        else:
            assert "Authorization" not in request.headers
        prompt = unquote(request.url.raw_path.split(b"?", 1)[0].decode())
        assert title in prompt
        assert "мультяшную" in prompt and "слева" in prompt and "Без надписей" in prompt
        return httpx.Response(200, content=payload)

    assert asyncio.run(fetch_cartoon_background(title, transport=httpx.MockTransport(respond))) == payload


@pytest.mark.parametrize("status", [403, 429, 503])
def test_provider_errors_stop_after_one_request(status):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status)

    assert asyncio.run(fetch_cartoon_background("Ужин", transport=httpx.MockTransport(respond))) is None
    assert len(requests) == 1


def test_slow_download_is_cancelled():
    cancelled = []

    async def respond(request):
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)

    result = asyncio.run(fetch_cartoon_background("Ужин", transport=httpx.MockTransport(respond), timeout=0.05))
    assert result is None
    assert cancelled == [True]


def test_save_and_render_uses_custom_background():
    slug = "abc123custombg01"
    # Distinct bright color so default night bg differs
    raw = BytesIO()
    Image.new("RGB", (800, 400), (255, 0, 0)).save(raw, format="JPEG", quality=90)
    path = save_generated_background(slug, raw.getvalue())
    assert path is not None
    assert background_path_for(slug) == path

    jpeg = render_event_og_jpeg("Красный фон", slug=slug)
    assert jpeg[:3] == b"\xff\xd8\xff"
    # Default-only render should still work
    default_jpeg = render_event_og_jpeg("Красный фон")
    assert default_jpeg[:3] == b"\xff\xd8\xff"
    assert len(jpeg) > 5_000

    delete_background_for(slug)
    assert background_path_for(slug) is None


def test_generate_and_store_persists_when_fetch_ok(monkeypatch):
    slug = "genstoreokslug001"
    monkeypatch.setattr(
        "app.pollinations.fetch_cartoon_background",
        AsyncMock(return_value=_tiny_jpeg_bytes((10, 200, 10))),
    )
    # Call the real function (autouse mock targets app.og_image.generate_and_store_background
    # only when scheduled via routes — call module function directly).
    from app import og_image

    asyncio.run(og_image.generate_and_store_background(slug, "Пикник"))
    assert background_path_for(slug) is not None
    delete_background_for(slug)


def test_generate_and_store_noop_when_fetch_fails(monkeypatch):
    slug = "genstorefailslug01"
    monkeypatch.setattr("app.pollinations.fetch_cartoon_background", AsyncMock(return_value=None))
    from app import og_image

    asyncio.run(og_image.generate_and_store_background(slug, "Ничего"))
    assert background_path_for(slug) is None


def test_og_route_ok_without_ai_background(client):
    slug = client.post("/events", data={"name": "Без AI"}, follow_redirects=False).headers[
        "location"
    ].split("/e/")[1]
    response = client.get(f"/og/{slug}.jpg")
    assert response.status_code == 200
    assert response.content == client.get("/og/site.jpg").content


def test_invalid_provider_image_leaves_homepage_card(client, monkeypatch):
    from app.og_image import generate_and_store_background

    monkeypatch.setattr("app.routes.events.generate_and_store_background", generate_and_store_background)
    monkeypatch.setattr("app.pollinations.fetch_cartoon_background", AsyncMock(return_value=b"invalid image"))
    response = client.post("/events", data={"name": "Пикник"}, follow_redirects=False)
    assert response.status_code == 303
    slug = response.headers["location"].split("/")[-1]
    assert background_path_for(slug) is None
    assert client.get(f"/og/{slug}.jpg").content == client.get("/og/site.jpg").content


def test_og_route_uses_saved_background(client):
    slug = client.post("/events", data={"name": "С AI"}, follow_redirects=False).headers[
        "location"
    ].split("/e/")[1]
    raw = BytesIO()
    Image.new("RGB", (1200, 630), (0, 180, 255)).save(raw, format="JPEG")
    save_generated_background(slug, raw.getvalue())

    response = client.get(f"/og/{slug}.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content != client.get("/og/site.jpg").content
    assert len(response.content) > 5_000


def test_cleanup_removes_og_file(client):
    from datetime import datetime, timedelta, timezone

    from app import crud
    from app.cleanup import cleanup_old_events
    from app.db import SessionLocal

    slug = client.post("/events", data={"name": "Старое OG"}, follow_redirects=False).headers[
        "location"
    ].split("/e/")[1]
    raw = BytesIO()
    Image.new("RGB", (100, 100), (90, 90, 90)).save(raw, format="JPEG")
    save_generated_background(slug, raw.getvalue())
    assert background_path_for(slug) is not None

    db = SessionLocal()
    try:
        event = crud.get_event_by_slug(db, slug)
        event.created_at = datetime.now(timezone.utc) - timedelta(days=400)
        db.commit()
    finally:
        db.close()

    deleted = cleanup_old_events()
    assert deleted >= 1
    assert background_path_for(slug) is None
    assert not (Path(OG_IMAGE_DIR) / f"{slug}.jpg").exists()


def test_cleanup_purges_orphan_og_files_by_mtime(client):
    import os
    from datetime import datetime, timedelta, timezone

    from app.cleanup import RETENTION_DAYS, cleanup_old_events
    from app.og_image import cleanup_stale_og_backgrounds

    orphan = Path(OG_IMAGE_DIR) / "orphanoldslug0001.jpg"
    Image.new("RGB", (80, 80), (1, 2, 3)).save(orphan, format="JPEG")
    old_ts = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS + 10)).timestamp()
    os.utime(orphan, (old_ts, old_ts))

    fresh = Path(OG_IMAGE_DIR) / "freshslugkeep0001.jpg"
    Image.new("RGB", (80, 80), (4, 5, 6)).save(fresh, format="JPEG")

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    purged = cleanup_stale_og_backgrounds(cutoff)
    assert purged >= 1
    assert not orphan.exists()
    assert fresh.exists()

    # Full cleanup job also runs the purge
    Image.new("RGB", (80, 80), (7, 8, 9)).save(orphan, format="JPEG")
    os.utime(orphan, (old_ts, old_ts))
    cleanup_old_events()
    assert not orphan.exists()
