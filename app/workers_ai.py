"""Generate an illustrated background for an event."""

import asyncio
import base64
import logging
import os
from urllib.parse import quote

import httpx


def build_prompt(event_name: str) -> str:
    """Describe the illustration in Russian using the original event title."""
    title = event_name.strip() or "Событие"
    return (
        f"Нарисуй яркую мультяшную иллюстрацию для события «{title}». "
        "Широкий горизонтальный кадр, дружеская атмосфера. "
        "Оставь слева место для заголовка. Без надписей, логотипов и водяных знаков."
    )


def _credentials() -> tuple[str, str]:
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    return account, token


def workers_ai_configured() -> bool:
    """Return whether the account and API token are both configured."""
    return all(_credentials())


async def fetch_cartoon_background(
    event_name: str, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 10
) -> bytes | None:
    """Fetch one image within a total deadline, returning None on timeout or failure."""
    account, token = _credentials()
    if not account or not token:
        return None

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{quote(account, safe='')}/ai/run/"
        "@cf/black-forest-labs/flux-1-schnell"
    )
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    json={"prompt": build_prompt(event_name), "steps": 4},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("success") is not True:
                    return None
                result = payload.get("result")
                if not isinstance(result, dict) or not isinstance(result.get("image"), str):
                    return None
                return base64.b64decode(result["image"], validate=True) or None
    except (TimeoutError, httpx.HTTPError, ValueError) as exc:
        logging.getLogger(__name__).warning("Workers AI request failed (%s)", type(exc).__name__)
        return None
