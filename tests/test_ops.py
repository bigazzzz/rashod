import os
from io import BytesIO

from PIL import Image


def test_ops_disabled_without_token(client, monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "")
    # Force re-read: ops module caches at import — patch the module constant
    import app.routes.ops as ops

    monkeypatch.setattr(ops, "OPS_TOKEN", "")
    response = client.get("/internal/ops/health", headers={"X-Ops-Token": "anything"})
    assert response.status_code == 404


def test_ops_rejects_wrong_token(client, monkeypatch):
    import app.routes.ops as ops

    monkeypatch.setattr(ops, "OPS_TOKEN", "secret-ops")
    response = client.get("/internal/ops/health")
    assert response.status_code == 401
    response = client.get("/internal/ops/health", headers={"X-Ops-Token": "wrong"})
    assert response.status_code == 401


def test_ops_health_ok(client, monkeypatch):
    import app.routes.ops as ops

    monkeypatch.setattr(ops, "OPS_TOKEN", "secret-ops")
    monkeypatch.setenv("POLLINATIONS_API_KEY", "pk-test")
    response = client.get("/internal/ops/health", headers={"X-Ops-Token": "secret-ops"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db_ok"] is True
    assert data["og_dir_exists"] is True
    assert data["pollinations_configured"] is True
    assert "version" in data
    assert data["retention_days"] == 365
    assert "public_base_url_set" in data
    assert "POLLINATIONS" not in str(data).upper() or data["pollinations_configured"] is True
    assert "pk-test" not in response.text


def test_ops_stats_and_event_info_no_pii(client, monkeypatch):
    import app.routes.ops as ops
    from app.og_image import save_generated_background

    monkeypatch.setattr(ops, "OPS_TOKEN", "secret-ops")
    headers = {"X-Ops-Token": "secret-ops"}

    create = client.post("/events", data={"name": "Ops Meta"}, follow_redirects=False)
    slug = create.headers["location"].split("/e/")[1]
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "СекретноеИмя", "description": "тайна", "amount": "42.50"},
        follow_redirects=False,
    )
    raw = BytesIO()
    Image.new("RGB", (100, 100), (1, 2, 3)).save(raw, format="JPEG")
    save_generated_background(slug, raw.getvalue())

    stats = client.get("/internal/ops/stats", headers=headers)
    assert stats.status_code == 200
    body = stats.json()
    assert body["events"] >= 1
    assert body["expenses"] >= 1
    assert body["og_files"] >= 1
    assert body["unique_participants"]["distinct_payer_names"] >= 1
    assert "meaning" in body["unique_participants"]
    assert "events_created_total" in body["counters"]
    assert "СекретноеИмя" not in stats.text

    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "СекретноеИмя", "description": "ещё", "amount": "1"},
        follow_redirects=False,
    )
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Другой", "description": "x", "amount": "2"},
        follow_redirects=False,
    )
    stats2 = client.get("/internal/ops/stats", headers=headers).json()
    assert stats2["unique_participants"]["distinct_payer_names"] >= 2

    info = client.get(f"/internal/ops/event/{slug}", headers=headers)
    assert info.status_code == 200
    meta = info.json()
    assert meta["slug"] == slug
    assert meta["name"] == "Ops Meta"
    assert meta["expense_count"] == 3
    assert meta["has_og_background"] is True
    assert f"/e/{slug}" in meta["urls"]["event"]
    assert "СекретноеИмя" not in info.text
    assert "тайна" not in info.text
    assert "42.50" not in info.text


def test_ops_event_not_found(client, monkeypatch):
    import app.routes.ops as ops

    monkeypatch.setattr(ops, "OPS_TOKEN", "secret-ops")
    response = client.get(
        "/internal/ops/event/deadbeefdeadbeef00",
        headers={"X-Ops-Token": "secret-ops"},
    )
    assert response.status_code == 404


def test_ops_metrics_summary_and_public_checks(client, monkeypatch):
    import app.routes.ops as ops

    monkeypatch.setattr(ops, "OPS_TOKEN", "secret-ops")
    headers = {"X-Ops-Token": "secret-ops"}

    metrics = client.get("/internal/ops/metrics/summary", headers=headers)
    assert metrics.status_code == 200
    assert "samples" in metrics.json()

    checks = client.get("/internal/ops/public-checks", headers=headers)
    assert checks.status_code == 200
    payload = checks.json()
    assert "checks" in payload
    paths = {c["path"] for c in payload["checks"]}
    assert "/healthz" in paths
    assert "/" in paths
    assert "/og/site.jpg" in paths
    for item in payload["checks"]:
        assert "status_code" in item
        assert "latency_ms" in item
