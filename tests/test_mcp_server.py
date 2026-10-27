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


def test_ops_get_unauthorized(monkeypatch):
    from mcp_server import client as ops_client
    from mcp_server.client import OpsClientError

    monkeypatch.setattr(ops_client, "OPS_BASE_URL", "http://web:8000")
    monkeypatch.setattr(ops_client, "OPS_TOKEN", "tok")

    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch("mcp_server.client.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
        with pytest.raises(OpsClientError, match="unauthorized"):
            ops_client.ops_get("/internal/ops/health")


def test_mcp_http_requires_bearer(monkeypatch):
    monkeypatch.setenv("MCP_TOKEN", "mcp-secret")
    from mcp_server import auth as auth_mod

    monkeypatch.setattr(auth_mod, "MCP_TOKEN", "mcp-secret")

    # Rebuild app with patched token
    from mcp_server.server import create_http_app

    app = create_http_app()
    # Middleware already bound MCP_TOKEN at import — re-add with patched module
    # create_http_app reads middleware classes that use module-level MCP_TOKEN
    with TestClient(app) as client:
        denied = client.post("/mcp", json={})
        assert denied.status_code == 401
        ok_headers = {"Authorization": "Bearer mcp-secret"}
        # May be 400/406 for bad MCP payload, but not 401
        allowed = client.post("/mcp", headers=ok_headers, json={})
        assert allowed.status_code != 401


def test_event_info_rejects_bad_slug(monkeypatch):
    monkeypatch.setenv("MCP_TOKEN", "x")
    from mcp_server.server import event_info

    result = json.loads(event_info("not-a-slug"))
    assert "error" in result
    assert "Invalid slug" in result["error"]


def test_health_tool_uses_ops_client(monkeypatch):
    from mcp_server.server import health

    with patch("mcp_server.server.ops_get", return_value={"status": "ok", "version": "0.17.0"}):
        payload = json.loads(health())
    assert payload["status"] == "ok"
    assert payload["version"] == "0.17.0"
