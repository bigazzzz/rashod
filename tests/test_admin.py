import re


def _enable_admin(monkeypatch, password="admin-secret"):
    import app.routes.admin as admin

    monkeypatch.setattr(admin, "ADMIN_PASSWORD", password)
    monkeypatch.setattr(admin, "ADMIN_SESSION_SECRET", "session-secret-for-tests")
    return admin


def _csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match, "csrf_token not found"
    return match.group(1)


def _login(client, monkeypatch, password="admin-secret"):
    _enable_admin(monkeypatch, password=password)
    page = client.get("/admin/login")
    assert page.status_code == 200
    token = _csrf_from(page.text)
    resp = client.post(
        "/admin/login",
        data={"password": password, "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/"
    return client


def test_admin_disabled_without_secrets(client, monkeypatch):
    import app.routes.admin as admin

    monkeypatch.setattr(admin, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(admin, "ADMIN_SESSION_SECRET", "")
    assert client.get("/admin/").status_code == 404
    assert client.get("/admin/login").status_code == 404


def test_admin_login_flow_and_dashboard_tops(client, monkeypatch):
    _login(client, monkeypatch)

    client.post("/events", data={"name": "Admin Party"}, follow_redirects=False)
    # find slug from list after creating via API path
    create = client.post("/events", data={"name": "Top Event"}, follow_redirects=False)
    slug = create.headers["location"].split("/e/")[1]
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "HiddenName", "description": "Общий ужин", "amount": "100"},
        follow_redirects=False,
    )
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "HiddenName", "description": "общий ужин", "amount": "50"},
        follow_redirects=False,
    )

    dash = client.get("/admin/?days=30")
    assert dash.status_code == 200
    assert "Дашборд" in dash.text
    assert "Топ-20 событий" in dash.text
    assert "Топ-20 назначений" in dash.text
    assert "eventsChart" in dash.text
    assert "Top Event" in dash.text
    assert "Общий ужин" in dash.text or "общий ужин" in dash.text
    assert "HiddenName" not in dash.text


def test_admin_rejects_bad_password(client, monkeypatch):
    _enable_admin(monkeypatch)
    page = client.get("/admin/login")
    token = _csrf_from(page.text)
    resp = client.post(
        "/admin/login",
        data={"password": "wrong", "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "login" in resp.headers["location"]


def test_admin_requires_csrf_on_logout(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.post("/admin/logout", data={"csrf_token": "bad"}, follow_redirects=False)
    assert resp.status_code == 403


def test_admin_delete_event(client, monkeypatch):
    _login(client, monkeypatch)
    create = client.post("/events", data={"name": "To Delete"}, follow_redirects=False)
    slug = create.headers["location"].split("/e/")[1]
    detail = client.get(f"/admin/events/{slug}")
    assert detail.status_code == 200
    assert "To Delete" in detail.text
    assert "HiddenName" not in detail.text
    token = _csrf_from(detail.text)
    deleted = client.post(
        f"/admin/events/{slug}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert client.get(f"/e/{slug}").status_code == 404


def test_admin_events_search_and_checks(client, monkeypatch):
    _login(client, monkeypatch)
    create = client.post("/events", data={"name": "Searchable"}, follow_redirects=False)
    slug = create.headers["location"].split("/e/")[1]
    listed = client.get("/admin/events?q=Search")
    assert listed.status_code == 200
    assert slug in listed.text
    checks = client.get("/admin/checks")
    assert checks.status_code == 200
    assert "/healthz" in checks.text


def test_robots_disallow_admin(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert "Disallow: /admin" in resp.text
