from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.og_image import (
    OG_IMAGE_DIR,
    WIDTH,
    HEIGHT,
    background_path_for,
    delete_background_for,
    generate_and_store_background,
    render_event_og_jpeg,
    save_generated_background,
)
from app.pollinations import build_prompt, fetch_cartoon_background


def _tiny_jpeg_bytes(color=(40, 80, 120)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="JPEG")
    return buf.getvalue()


def test_build_prompt_mentions_title_and_no_text():
    prompt = build_prompt("Поход на Алтай")
    assert "Поход на Алтай" in prompt
    assert "no text" in prompt
    assert "cartoon" in prompt.lower()


def test_fetch_returns_none_on_http_error_real_type():
    import urllib.error

    def boom(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="http://x", code=500, msg="err", hdrs=None, fp=None
        )

    with patch("app.pollinations.urllib.request.urlopen", side_effect=boom):
        with patch("app.pollinations.time.sleep", return_value=None):
            assert fetch_cartoon_background("test") is None


def test_fetch_returns_none_on_client_error_without_retry_storm():
    import urllib.error

    calls = {"n": 0}

    def boom(*_args, **_kwargs):
        calls["n"] += 1
        raise urllib.error.HTTPError(
            url="http://x", code=403, msg="forbidden", hdrs=None, fp=None
        )

    with patch("app.pollinations.urllib.request.urlopen", side_effect=boom):
        with patch("app.pollinations.time.sleep", return_value=None):
            assert fetch_cartoon_background("test") is None
    assert calls["n"] == 1


def test_fetch_returns_bytes_on_success():
    payload = _tiny_jpeg_bytes() * 20  # > 1000 bytes

    class Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("app.pollinations.urllib.request.urlopen", return_value=Resp()):
        assert fetch_cartoon_background("Ужин") == payload


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
        lambda name: _tiny_jpeg_bytes((10, 200, 10)) * 30,
    )
    # Call the real function (autouse mock targets app.og_image.generate_and_store_background
    # only when scheduled via routes — call module function directly).
    from app import og_image

    og_image.generate_and_store_background(slug, "Пикник")
    assert background_path_for(slug) is not None
    delete_background_for(slug)


def test_generate_and_store_noop_when_fetch_fails(monkeypatch):
    slug = "genstorefailslug01"
    monkeypatch.setattr("app.pollinations.fetch_cartoon_background", lambda name: None)
    from app import og_image

    og_image.generate_and_store_background(slug, "Ничего")
    assert background_path_for(slug) is None


def test_og_route_ok_without_ai_background(client):
    slug = client.post("/events", data={"name": "Без AI"}, follow_redirects=False).headers[
        "location"
    ].split("/e/")[1]
    response = client.get(f"/og/{slug}.jpg")
    assert response.status_code == 200
    assert response.content[:3] == b"\xff\xd8\xff"


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
