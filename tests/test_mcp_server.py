import json
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient


def test_ops_get_success(monkeypatch):
    from mcp_server import client as ops_client

    monkeypatch.setattr(ops_client, "OPS_BASE_URL", "http://web:8000")
    monkeypatch.setattr(ops_client, "OPS_TOKEN", "tok")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}

    with patch("mcp_server.client.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
        data = ops_client.ops_get("/internal/ops/health")
    assert data["status"] == "ok"
    call_kwargs = client_cls.return_value.__enter__.return_value.get.call_args
    assert call_kwargs[1]["headers"]["X-Ops-Token"] == "tok"


def test_ops_post_returns_validation_detail(monkeypatch):
    from mcp_server import client as ops_client
    from mcp_server.client import OpsClientError

    monkeypatch.setattr(ops_client, "OPS_BASE_URL", "http://web:8000")
    monkeypatch.setattr(ops_client, "OPS_TOKEN", "tok")

    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"detail": "Название события не может быть пустым"}
    mock_resp.content = b"{}"

    with patch("mcp_server.client.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
        with pytest.raises(OpsClientError, match="не может быть пустым"):
            ops_client.ops_post("/internal/ops/events", {"name": ""})


def test_mcp_http_is_public(monkeypatch):
    monkeypatch.delenv("MCP_TOKEN", raising=False)
    from mcp_server.server import create_http_app

    app = create_http_app()
    with TestClient(app) as client:
        response = client.post("/mcp", json={})
    assert response.status_code != 401
    assert response.status_code != 503


def test_add_expense_rejects_bad_slug():
    from mcp_server.server import add_expense

    result = json.loads(add_expense("not-a-slug", amount="10"))
    assert "error" in result
    assert "slug" in result["error"]


def test_create_event_tool_uses_ops_client():
    from mcp_server.server import create_event

    payload = {
        "slug": "abc123abc123abc123",
        "name": "Пикник",
        "urls": {
            "event": "https://porovnu.su/e/abc123abc123abc123",
            "results": "https://porovnu.su/r/abc123abc123abc123",
        },
    }
    with patch("mcp_server.server.ops_post", return_value=payload) as post:
        result = json.loads(create_event("Пикник"))
    post.assert_called_once_with("/internal/ops/events", {"name": "Пикник"})
    assert result["slug"] == "abc123abc123abc123"
    assert result["urls"]["results"].endswith("/r/abc123abc123abc123")


def test_add_expense_tool_posts_fields():
    from mcp_server.server import add_expense

    slug = "abc123abc123abc123"
    payload = {
        "slug": slug,
        "payer_name": "User001",
        "description": "",
        "amount": "0.00",
        "urls": {"event": f"https://porovnu.su/e/{slug}"},
    }
    with patch("mcp_server.server.ops_post", return_value=payload) as post:
        result = json.loads(add_expense(slug, amount="0", description="скрыто"))
    post.assert_called_once_with(
        f"/internal/ops/events/{slug}/expenses",
        {"amount": "0", "description": "скрыто", "payer_name": ""},
    )
    assert result["payer_name"] == "User001"
    assert "скрыто" not in json.dumps(result, ensure_ascii=False)
