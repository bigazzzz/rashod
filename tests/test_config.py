import pytest

from app.rate_limit import _client_key
from app.routes.events import _validate_public_base_url


def test_validate_public_base_url_accepts_none():
    assert _validate_public_base_url(None) is None


def test_validate_public_base_url_accepts_empty_string_as_none():
    assert _validate_public_base_url("") is None


def test_validate_public_base_url_accepts_https():
    assert _validate_public_base_url("https://example.com") == "https://example.com"


def test_validate_public_base_url_accepts_http():
    assert _validate_public_base_url("http://example.com") == "http://example.com"


def test_validate_public_base_url_rejects_schemeless_value():
    with pytest.raises(ValueError, match="http:// or https://"):
        _validate_public_base_url("example.com")


class _FakeRequest:
    def __init__(self, headers: dict, client_host: str = "10.0.0.5"):
        self.headers = headers

        class _Client:
            host = client_host

        self.client = _Client()


def test_client_key_uses_remote_address_by_default(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    request = _FakeRequest(headers={"x-forwarded-for": "1.2.3.4"})
    assert _client_key(request) == "10.0.0.5"


def test_client_key_uses_forwarded_for_when_trusted(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    request = _FakeRequest(headers={"x-forwarded-for": "1.2.3.4, 10.0.0.1"})
    assert _client_key(request) == "1.2.3.4"


def test_client_key_falls_back_when_trusted_but_header_missing(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    request = _FakeRequest(headers={})
    assert _client_key(request) == "10.0.0.5"
