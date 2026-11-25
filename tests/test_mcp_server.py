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
    assert response.headers["x-request-id"]


def test_add_expense_rejects_bad_slug():
    from mcp_server.server import add_expense

    result = json.loads(add_expense("not-a-slug", amount="10"))
    assert "error" in result
    assert "slug" in result["error"]


def test_metrics_include_mcp_tool_outcomes():
    from mcp_server.server import add_expense, create_http_app

    add_expense("not-a-slug")
    response = TestClient(create_http_app()).get("/metrics")
    assert response.status_code == 200
    assert 'porovnu_mcp_tool_calls_total{outcome="rejected",tool="add_expense"}' in response.text
    assert 'porovnu_mcp_tool_duration_seconds_count{tool="add_expense"}' in response.text


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


def test_get_settlement_via_mcp():
    import asyncio
    from mcp.shared.memory import create_connected_server_and_client_session
    from mcp_server.server import mcp

    slug = "abc123abc123abc123"
    payload = {"total": "0.00", "participant_count": 0, "transfers": [], "urls": {"results": f"/r/{slug}"}}

    async def check():
        async with create_connected_server_and_client_session(mcp) as session:
            tools = (await session.list_tools()).tools
            assert next(t for t in tools if t.name == "get_settlement").annotations.readOnlyHint
            with patch("mcp_server.server.ops_get", return_value=payload) as get:
                invalid = await session.call_tool("get_settlement", {"slug": "../other"})
                assert "slug" in json.loads(invalid.content[0].text)["error"]
                get.assert_not_called()
                result = await session.call_tool("get_settlement", {"slug": slug})
                assert json.loads(result.content[0].text) == payload
                get.assert_called_once_with(f"/internal/ops/events/{slug}/settlement")

    asyncio.run(check())
