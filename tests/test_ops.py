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
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "pk-test")
    response = client.get("/internal/ops/health", headers={"X-Ops-Token": "secret-ops"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db_ok"] is True
    assert data["og_dir_exists"] is True
    assert data["workers_ai_configured"] is True
    assert "version" in data
    assert data["retention_days"] == 365
    assert "public_base_url_set" in data
    assert data["pollinations_configured"] is False
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


def test_prometheus_metrics_include_sqlite_filesystem(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    sample = next(line for line in response.text.splitlines() if line.startswith("porovnu_sqlite_storage_free_ratio "))
    assert 0 <= float(sample.split()[1]) <= 1


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


def test_ops_create_event_and_expense(client, monkeypatch):
    import app.routes.ops as ops

    monkeypatch.setattr(ops, "OPS_TOKEN", "secret-ops")
    monkeypatch.setattr(ops, "PUBLIC_BASE_URL", "https://porovnu.su")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        ops,
        "generate_and_store_background",
        lambda slug, name: calls.append((slug, name)),
    )
    headers = {"X-Ops-Token": "secret-ops"}

    denied = client.post("/internal/ops/events", json={"name": "Пикник"})
    assert denied.status_code == 401

    empty = client.post("/internal/ops/events", json={"name": "   "}, headers=headers)
    assert empty.status_code == 400
    assert "Название события не может быть пустым" in empty.json()["detail"]

    created = client.post("/internal/ops/events", json={"name": " Пикник "}, headers=headers)
    assert created.status_code == 200
    body = created.json()
    slug = body["slug"]
    assert body["name"] == "Пикник"
    assert body["urls"]["event"] == f"https://porovnu.su/e/{slug}"
    assert body["urls"]["results"] == f"https://porovnu.su/r/{slug}"
    assert calls == [(slug, "Пикник")]

    zero = client.post(
        f"/internal/ops/events/{slug}/expenses",
        json={"amount": "0", "description": "не должно сохраниться", "payer_name": ""},
        headers=headers,
    )
    assert zero.status_code == 200
    assert zero.json()["payer_name"] == "User001"
    assert zero.json()["description"] == ""
    assert zero.json()["amount"] == "0.00"
    assert zero.json()["urls"]["event"] == f"https://porovnu.su/e/{slug}"

    paid = client.post(
        f"/internal/ops/events/{slug}/expenses",
        json={"amount": "12,50", "description": " такси ", "payer_name": "Аня"},
        headers=headers,
    )
    assert paid.status_code == 200
    assert paid.json()["payer_name"] == "Аня"
    assert paid.json()["description"] == "такси"
    assert paid.json()["amount"] == "12.50"

    negative = client.post(
        f"/internal/ops/events/{slug}/expenses",
        json={"amount": "-1", "payer_name": "Аня"},
        headers=headers,
    )
    assert negative.status_code == 400
    assert "отрицательн" in negative.json()["detail"]


def test_expense_writes_share_auto_names_and_amount_validation(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.routes import ops

    monkeypatch.setattr(ops, "OPS_TOKEN", "test")
    headers = {"X-Ops-Token": "test"}
    event = client.post("/internal/ops/events", headers=headers, json={"name": "Тест"}).json()
    slug = event["slug"]
    url = f"/internal/ops/events/{slug}/expenses"
    client.post(f"/e/{slug}/expenses", data={"payer_name": "user001", "amount": "10"})
    for invalid in ["0.004", "100000000", "1.00000000000000000000000000001"]:
        assert client.post(url, headers=headers, json={"amount": invalid}).status_code == 400
        assert client.post(f"/e/{slug}/expenses", data={"amount": invalid}).status_code == 400
    assert client.post(url, headers=headers, json={"payer_name": "Аня", "amount": "99999999.990"}).status_code == 200

    def add_anonymous(_):
        return client.post(url, headers=headers, json={}).json()["payer_name"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        names = list(pool.map(add_anonymous, range(8)))
    assert sorted(names) == [f"User{i:03d}" for i in range(2, 10)]


def test_public_checks_do_not_start_cleanup(client, monkeypatch):
    from unittest.mock import Mock
    from app.routes import ops

    monkeypatch.setattr(ops, "OPS_TOKEN", "test")
    cleanup = Mock()
    monkeypatch.setattr("app.cleanup.cleanup_old_events", cleanup)
    response = client.get("/internal/ops/public-checks", headers={"X-Ops-Token": "test"})
    assert all(check["status_code"] == 200 for check in response.json()["checks"])
    cleanup.assert_not_called()
