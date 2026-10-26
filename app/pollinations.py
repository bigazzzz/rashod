"""Fetch cartoon OG backgrounds from Pollinations.ai (no key required)."""

from __future__ import annotations

import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("pollinations")

IMAGE_BASE = "https://image.pollinations.ai/prompt"
TIMEOUT_SECONDS = 45
MAX_ATTEMPTS = 3

# Longest phrases first — used to turn Russian event titles into English prompt subjects.
_RU_PHRASES: tuple[tuple[str, str], ...] = (
    ("день рождения", "birthday party"),
    ("новый год", "new year celebration"),
    ("корпоратив", "office party"),
    ("мальчишник", "bachelor party"),
    ("девичник", "bachelorette party"),
    ("юбилей", "anniversary celebration"),
    ("свадьба", "wedding"),
    ("пикник", "picnic"),
    ("шашлык", "barbecue picnic"),
    ("поход", "hiking trip"),
    ("путешествие", "travel adventure"),
    ("отпуск", "vacation"),
    ("вечеринка", "party"),
    ("встреча", "friendly gathering"),
    ("ужин", "dinner gathering"),
    ("обед", "lunch gathering"),
    ("завтрак", "breakfast gathering"),
    ("концерт", "concert"),
    ("фестиваль", "festival"),
    ("спорт", "sports event"),
    ("футбол", "football match"),
    ("баня", "sauna gathering"),
    ("дача", "countryside cottage"),
    ("ресторан", "restaurant dinner"),
    ("бар", "bar night out"),
    ("кино", "cinema night"),
    ("театр", "theater evening"),
    ("море", "seaside vacation"),
    ("горы", "mountain landscape"),
    ("парк", "park"),
    ("алтай", "Altai mountains"),
)

_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]+")
_SPACE_RE = re.compile(r"\s+")


def event_name_to_english(event_name: str) -> str:
    """Map a (often Russian) event title to a short English image-prompt subject."""
    raw = (event_name or "").strip()
    if not raw:
        return "celebration"

    # Already mostly Latin — keep the title, drop leftover Cyrillic names.
    if not _CYRILLIC_RE.search(raw):
        cleaned = _SPACE_RE.sub(" ", raw).strip(" ,.-")
        return cleaned or "celebration"

    text = raw.casefold()
    for ru, en in _RU_PHRASES:
        if ru in text:
            text = text.replace(ru, f" {en} ")

    # Drop remaining Cyrillic (personal names etc.) — model handles English better.
    text = _CYRILLIC_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip(" ,.-")
    return text or "celebration"


def build_prompt(event_name: str) -> str:
    subject = event_name_to_english(event_name)
    return (
        f"cartoon illustrated scene about: {subject}. "
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
