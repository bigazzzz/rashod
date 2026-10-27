"""HTTP client for the app's /internal/ops API."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

OPS_BASE_URL = (os.environ.get("OPS_BASE_URL") or "http://web:8000").rstrip("/")
OPS_TOKEN = (os.environ.get("OPS_TOKEN") or "").strip()


class OpsClientError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "porovnu-mcp/0.17"}
    if OPS_TOKEN:
        headers["X-Ops-Token"] = OPS_TOKEN
    return headers


def ops_get(path: str, *, timeout: float = 15.0) -> dict[str, Any]:
    url = f"{OPS_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=_headers())
    except httpx.HTTPError as exc:
        raise OpsClientError(f"Ops request failed: {type(exc).__name__}") from exc

    if response.status_code == 401:
        raise OpsClientError("Ops API unauthorized (check OPS_TOKEN)", status_code=401)
    if response.status_code == 404:
        raise OpsClientError("Not found", status_code=404)
    if response.status_code >= 400:
        raise OpsClientError(
            f"Ops API error HTTP {response.status_code}",
            status_code=response.status_code,
        )
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise OpsClientError("Ops API returned non-JSON") from exc
    if not isinstance(data, dict):
        raise OpsClientError("Ops API returned unexpected payload")
    return data
