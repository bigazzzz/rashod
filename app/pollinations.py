"""Fetch cartoon OG backgrounds from Pollinations.ai (no key required)."""

from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("pollinations")

IMAGE_BASE = "https://image.pollinations.ai/prompt"
TIMEOUT_SECONDS = 45
MAX_ATTEMPTS = 3


def build_prompt(event_name: str) -> str:
    title = (event_name or "celebration").strip() or "celebration"
    return (
        f"cartoon illustrated scene about: {title}. "
        "cute colorful cartoon style, friendly atmosphere, wide landscape composition, "
        "no text, no letters, no watermark, no logo, no typography"
    )


def fetch_cartoon_background(event_name: str) -> bytes | None:
    """Download a generated image, or return None on any failure."""
    prompt = build_prompt(event_name)
    params = urllib.parse.urlencode(
        {
            "width": "1200",
            "height": "630",
            "model": "flux",
            "nologo": "true",
        }
    )
    url = f"{IMAGE_BASE}/{urllib.parse.quote(prompt, safe='')}?{params}"

    headers = {
        "User-Agent": "porovnu-og/0.15 (+https://porovnu.su)",
        "Accept": "image/*",
    }
    api_key = (os.environ.get("POLLINATIONS_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                data = response.read()
            if not data or len(data) < 1000:
                raise ValueError(f"empty or tiny response ({len(data) if data else 0} bytes)")
            return data
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            status = getattr(exc, "code", None)
            # Do not retry clear client errors except rate limits
            if isinstance(exc, urllib.error.HTTPError) and status is not None:
                if 400 <= status < 500 and status != 429:
                    log.warning("Pollinations client error %s for %r: %s", status, event_name, exc)
                    return None
            log.warning(
                "Pollinations attempt %d/%d failed for %r: %s",
                attempt,
                MAX_ATTEMPTS,
                event_name,
                exc,
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(1.5 * attempt)
        except Exception as exc:  # noqa: BLE001 — never break event creation
            last_error = exc
            log.exception("Unexpected Pollinations error for %r", event_name)
            return None

    log.warning("Pollinations gave up for %r: %s", event_name, last_error)
    return None
