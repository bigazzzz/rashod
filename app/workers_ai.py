"""Generate an illustrated background for an event."""

import asyncio
import base64
import logging
import os
import re
from urllib.parse import quote

import httpx


PROMPT_LIMIT = 2048
NO_TEXT_IN_IMAGE = (
    "\nDo not render any text anywhere in the image. "
    "Use no letters, numbers, captions, logos, watermarks, or text-like marks. "
    "Leave signs and labels blank."
)


def default_prompt_template() -> str:
    """Return the initial editable template for new event covers."""
    return (
        "Нарисуй яркую мультяшную иллюстрацию для события «{event_name}». "
        "Широкий горизонтальный кадр, дружеская атмосфера. "
        "Оставь слева место для заголовка. Без надписей, логотипов и водяных знаков."
    )


def build_prompt(event_name: str, template: str | None = None) -> str:
    """Substitute the title literally and respect the model's 2048-character limit."""
    template = default_prompt_template() if template is None else template
    return template.replace("{event_name}", event_name.strip() or "Событие")[:PROMPT_LIMIT]


def _credentials() -> tuple[str, str]:
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    return account, token


def workers_ai_configured() -> bool:
    """Return whether the account and API token are both configured."""
    return all(_credentials())


async def _run_model(client: httpx.AsyncClient, model: str, inputs: dict) -> dict:
    response = await client.post(model, json=inputs)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("success") is True:
        result = payload.get("result")
        if isinstance(result, dict):
            return result
    return {}


async def fetch_cartoon_background(
    event_name: str, *, template: str | None = None, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 10
) -> bytes | None:
    """Translate Russian prompts and fetch the image within one shared deadline."""
    account, token = _credentials()
    if not account or not token:
        return None

    base_url = f"https://api.cloudflare.com/client/v4/accounts/{quote(account, safe='')}/ai/run/"
    prompt = build_prompt(event_name, template)
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                base_url=base_url, headers={"Authorization": f"Bearer {token}"},
                transport=transport, timeout=timeout,
            ) as client:
                if re.search(r"[А-Яа-яЁё]", prompt):
                    translation = await _run_model(client, "@cf/meta/m2m100-1.2b", {
                        "text": prompt, "source_lang": "russian", "target_lang": "english",
                    })
                    english = translation.get("translated_text")
                    if not isinstance(english, str) or not english.strip():
                        return None
                    prompt = english.strip()

                prompt = prompt[:PROMPT_LIMIT - len(NO_TEXT_IN_IMAGE)].rstrip() + NO_TEXT_IN_IMAGE
                result = await _run_model(client, "@cf/black-forest-labs/flux-1-schnell", {
                    "prompt": prompt, "steps": 4,
                })
                image = result.get("image")
                if not isinstance(image, str):
                    return None
                return base64.b64decode(image, validate=True) or None
    except (TimeoutError, httpx.HTTPError, ValueError) as exc:
        logging.getLogger(__name__).warning("Workers AI request failed (%s)", type(exc).__name__)
        return None
