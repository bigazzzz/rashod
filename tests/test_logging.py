import json
import logging
import subprocess
import sys


def test_request_levels_and_private_fields(client, caplog):
    with caplog.at_level(logging.DEBUG, logger="porovnu.http"):
        health = client.get("/healthz")
        event = client.get(
            "/e/private-slug?note=private-query",
            headers={"Authorization": "Bearer private-token"},
        )

    assert health.status_code == 200
    assert event.status_code == 404
    assert health.headers["x-request-id"] != event.headers["x-request-id"]
    health_log, event_log = [r for r in caplog.records if r.name == "porovnu.http"]
    assert health_log.levelno == logging.DEBUG
    assert event_log.levelno == logging.WARNING
    assert event_log.fields["route"] == "/e/{slug}"
    assert event_log.fields["status"] == 404
    assert event_log.fields["duration_ms"] >= 0
    assert "private-" not in str(event_log.fields)


def test_config_filters_stdout_and_honors_mcp_override(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("MCP_LOG_LEVEL", "DEBUG")
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import logging; from porovnu_logging import configure_logging; "
            "configure_logging('web'); logging.info('hidden'); logging.warning('web warning'); "
            "configure_logging('mcp'); logging.debug('mcp debug')",
        ],
        capture_output=True, text=True, check=True,
    )
    web, mcp = map(json.loads, result.stdout.splitlines())
    assert (web["service"], web["level"], web["message"]) == ("web", "WARNING", "web warning")
    assert (mcp["service"], mcp["level"], mcp["message"]) == ("mcp", "DEBUG", "mcp debug")
