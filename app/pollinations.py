"""Generate an illustrated background for an event."""

import asyncio
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


async def fetch_cartoon_background(
    event_name: str, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 10
) -> bytes | None:
    """Fetch one image within a total deadline, returning None on timeout or failure."""
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    headers = {"Accept": "image/*"}
    if key:
        endpoint = "https://gen.pollinations.ai/image"
        headers["Authorization"] = f"Bearer {key}"
    else:
        endpoint = "https://image.pollinations.ai/prompt"
    url = f"{endpoint}/{quote(build_prompt(event_name), safe='')}"
    params = {"width": 1200, "height": 630, "nologo": "true"}
    if not key:
        params["model"] = "flux"
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.content or None
    except (TimeoutError, httpx.HTTPError) as exc:
        logging.getLogger(__name__).warning("Background request failed (%s)", type(exc).__name__)
        return None
