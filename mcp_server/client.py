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
    headers = {"Accept": "application/json", "User-Agent": "porovnu-mcp/0.19"}
    if OPS_TOKEN:
        headers["X-Ops-Token"] = OPS_TOKEN
    return headers


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"Ops API error HTTP {response.status_code}"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail
    return f"Ops API error HTTP {response.status_code}"


def _parse(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 401:
        raise OpsClientError("Ops API unauthorized (check OPS_TOKEN)", status_code=401)
    if response.status_code == 404:
        raise OpsClientError(_error_message(response) if response.content else "Not found", status_code=404)
    if response.status_code >= 400:
        raise OpsClientError(_error_message(response), status_code=response.status_code)
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise OpsClientError("Ops API returned non-JSON") from exc
    if not isinstance(data, dict):
        raise OpsClientError("Ops API returned unexpected payload")
    return data


def ops_get(path: str, *, timeout: float = 15.0) -> dict[str, Any]:
    url = f"{OPS_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=_headers())
    except httpx.HTTPError as exc:
        raise OpsClientError(f"Ops request failed: {type(exc).__name__}") from exc
    return _parse(response)


def ops_post(path: str, body: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    url = f"{OPS_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=_headers(), json=body)
    except httpx.HTTPError as exc:
        raise OpsClientError(f"Ops request failed: {type(exc).__name__}") from exc
    return _parse(response)
