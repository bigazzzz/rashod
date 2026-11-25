from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.workers_ai import default_prompt_template

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

WIDTH = 1200
HEIGHT = 630
BG_PATH = Path(__file__).parent / "static" / "og-bg.jpg"
OG_IMAGE_DIR = Path(os.environ.get("OG_IMAGE_DIR", "/data/og"))

log = logging.getLogger("og_image")


@lru_cache(maxsize=1)
def _load_default_background() -> Image.Image:
    image = Image.open(BG_PATH).convert("RGB")
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"), size)


def _split_oversized_word(
    draw: ImageDraw.ImageDraw, word: str, font: ImageFont.ImageFont, max_width: int
) -> list[str]:
    """Break a single word that is wider than max_width into character chunks."""
    if draw.textlength(word, font=font) <= max_width:
        return [word]
    chunks: list[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if current and draw.textlength(candidate, font=font) > max_width:
            chunks.append(current)
            current = char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    *,
    max_lines: int = 3,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    tokens: list[tuple[str, bool]] = []
    for word in words:
        parts = _split_oversized_word(draw, word, font, max_width)
        for index, part in enumerate(parts):
            tokens.append((part, index > 0))

    lines: list[str] = []
    current = ""
    for token, glue in tokens:
        if not current:
            current = token
            continue
        candidate = current + token if glue else f"{current} {token}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = token
    lines.append(current)

    if len(lines) <= max_lines:
        return lines

    kept = lines[:max_lines]
    last = kept[-1]
    ellipsis = "…"
    while last and draw.textlength(last + ellipsis, font=font) > max_width:
        last = last[:-1]
    kept[-1] = (last.rstrip() + ellipsis) if last else ellipsis
    return kept


def _draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
) -> None:
    x, y = xy
    shadow = (0, 0, 0, 160)
    for dx, dy in ((2, 2), (0, 2), (2, 0)):
        draw.text((x + dx, y + dy), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def background_path_for(slug: str) -> Path | None:
    path = OG_IMAGE_DIR / f"{slug}.jpg"
    return path if path.is_file() else None


def delete_background_for(slug: str) -> None:
    path = OG_IMAGE_DIR / f"{slug}.jpg"
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("Failed to delete OG background for %s: %s", slug, exc)


def cleanup_stale_og_backgrounds(cutoff: datetime) -> int:
    """Delete AI OG backgrounds older than cutoff (by file mtime). Returns count removed."""
    if not OG_IMAGE_DIR.is_dir():
        return 0
    cutoff_ts = cutoff.timestamp()
    removed = 0
    for path in OG_IMAGE_DIR.glob("*.jpg"):
        if path.name.startswith("."):
            continue
        try:
            if path.stat().st_mtime < cutoff_ts:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError as exc:
            log.warning("Failed to purge stale OG file %s: %s", path, exc)
    return removed


def compose_og(event_name: str, background: Image.Image) -> Image.Image:
    base = background.convert("RGBA")
    if base.size != (WIDTH, HEIGHT):
        base = base.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for x in range(WIDTH):
        t = x / (WIDTH - 1)
        alpha = int(150 * (1 - t) ** 1.35 + 55)
        draw.line([(x, 0), (x, HEIGHT)], fill=(6, 8, 18, alpha))

    for y in range(HEIGHT - 180, HEIGHT):
        t = (y - (HEIGHT - 180)) / 180
        alpha = int(90 * t)
        draw.line([(0, y), (WIDTH, y)], fill=(8, 6, 16, alpha))

    brand_font = _load_font(34)
    title_font = _load_font(68)

    brand = "Поровну"
    _draw_text_with_shadow(draw, (88, 96), brand, brand_font, (240, 184, 78, 255))
    draw.rounded_rectangle((88, 142, 172, 146), radius=2, fill=(255, 138, 61, 230))

    name = (event_name or "Событие").strip() or "Событие"
    lines = _wrap_text(draw, name, title_font, WIDTH - 220)
    y = 210
    for line in lines:
        _draw_text_with_shadow(draw, (88, y), line, title_font, (255, 246, 230, 255))
        bbox = draw.textbbox((0, 0), line, font=title_font)
        y += (bbox[3] - bbox[1]) + 10

    composed = Image.alpha_composite(base, overlay).convert("RGB")
    return composed.filter(ImageFilter.UnsharpMask(radius=1.1, percent=105, threshold=2))


@lru_cache(maxsize=256)
def _render_cached(slug: str, event_name: str, bg_mtime_ns: int) -> bytes:
    if bg_mtime_ns:
        try:
            with Image.open(OG_IMAGE_DIR / f"{slug}.jpg") as image:
                background = image.convert("RGB")
        except OSError:
            return render_site_og_jpeg()
    elif slug:
        return render_site_og_jpeg()
    else:
        background = _load_default_background()
    buf = BytesIO()
    compose_og(event_name, background).save(
        buf, format="JPEG", quality=85, optimize=True, progressive=True
    )
    return buf.getvalue()


def render_event_og_jpeg(event_name: str, slug: str | None = None) -> bytes:
    """Compose OG card. Optional slug picks AI background from OG_IMAGE_DIR."""
    if not slug:
        return _render_cached("", event_name, 0)

    path = background_path_for(slug)
    mtime_ns = path.stat().st_mtime_ns if path is not None else 0
    return _render_cached(slug, event_name, mtime_ns)


def render_site_og_jpeg() -> bytes:
    """Return the homepage card, also used until an event background is available."""
    return render_event_og_jpeg("Посчитать поровну чек")


def save_generated_background(slug: str, image_bytes: bytes) -> Path | None:
    """Resize/normalize Cloudflare Workers AI image and store as JPEG under OG_IMAGE_DIR."""
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image = ImageOps.fit(image, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    except OSError as exc:
        log.warning("Cannot decode generated background for %s: %s", slug, exc)
        return None

    OG_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    final_path = OG_IMAGE_DIR / f"{slug}.jpg"
    tmp_path = OG_IMAGE_DIR / f".{slug}.jpg.tmp"
    try:
        image.save(tmp_path, format="JPEG", quality=88, optimize=True)
        tmp_path.replace(final_path)
    except OSError as exc:
        log.warning("Cannot save OG background for %s: %s", slug, exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    _render_cached.cache_clear()
    return final_path


def read_cover_prompt() -> str:
    """Read the template from the persistent cover volume, defaulting on first use."""
    try:
        return (OG_IMAGE_DIR / "cover-prompt.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        return default_prompt_template()


def save_cover_prompt(template: str) -> None:
    """Replace the saved template atomically so concurrent jobs read complete text."""
    OG_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=OG_IMAGE_DIR, mode="w", encoding="utf-8", delete=False) as file:
        pending = Path(file.name)
        try:
            file.write(template)
            file.flush()
            pending.replace(OG_IMAGE_DIR / "cover-prompt.txt")
        finally:
            pending.unlink(missing_ok=True)


async def generate_and_store_background(slug: str, event_name: str) -> None:
    """Background job: fetch from Cloudflare Workers AI and persist, or no-op on failure."""
    from app.workers_ai import fetch_cartoon_background

    template = await asyncio.to_thread(read_cover_prompt)
    raw = await fetch_cartoon_background(event_name, template=template)
    if not raw:
        return
    path = await asyncio.to_thread(save_generated_background, slug, raw)
    if path:
        log.info("Stored Cloudflare Workers AI OG background for %s at %s", slug, path)
