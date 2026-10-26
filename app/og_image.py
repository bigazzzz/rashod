from __future__ import annotations

import logging
import os
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

WIDTH = 1200
HEIGHT = 630
BG_PATH = Path(__file__).parent / "static" / "og-bg.jpg"
OG_IMAGE_DIR = Path(os.environ.get("OG_IMAGE_DIR", "/data/og"))

_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
)

log = logging.getLogger("og_image")


@lru_cache(maxsize=1)
def _load_default_background() -> Image.Image:
    image = Image.open(BG_PATH).convert("RGB")
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


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


def _load_background_image(path: Path | None) -> Image.Image:
    if path is None:
        return _load_default_background().copy()
    try:
        image = Image.open(path).convert("RGB")
        return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    except OSError as exc:
        log.warning("Bad OG background %s (%s); using default", path, exc)
        return _load_default_background().copy()


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
    subtitle_font = _load_font(28)

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

    _draw_text_with_shadow(
        draw,
        (88, HEIGHT - 108),
        "Посчитать расходы поровну",
        subtitle_font,
        (210, 190, 160, 255),
    )

    composed = Image.alpha_composite(base, overlay).convert("RGB")
    return composed.filter(ImageFilter.UnsharpMask(radius=1.1, percent=105, threshold=2))


@lru_cache(maxsize=256)
def _render_cached(slug: str, event_name: str, bg_mtime_ns: int) -> bytes:
    path: Path | None = None
    if bg_mtime_ns > 0:
        candidate = OG_IMAGE_DIR / f"{slug}.jpg"
        if candidate.is_file():
            path = candidate
    buf = BytesIO()
    compose_og(event_name, _load_background_image(path)).save(
        buf, format="JPEG", quality=85, optimize=True, progressive=True
    )
    return buf.getvalue()


def render_event_og_jpeg(event_name: str, slug: str | None = None) -> bytes:
    """Compose OG card. Optional slug picks AI background from OG_IMAGE_DIR."""
    if not slug:
        buf = BytesIO()
        compose_og(event_name, _load_default_background().copy()).save(
            buf, format="JPEG", quality=85, optimize=True, progressive=True
        )
        return buf.getvalue()

    path = background_path_for(slug)
    mtime_ns = path.stat().st_mtime_ns if path is not None else 0
    return _render_cached(slug, event_name, mtime_ns)


def save_generated_background(slug: str, image_bytes: bytes) -> Path | None:
    """Resize/normalize Pollinations image and store as JPEG under OG_IMAGE_DIR."""
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
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


def generate_and_store_background(slug: str, event_name: str) -> None:
    """Background job: fetch from Pollinations and persist, or no-op on failure."""
    from app.pollinations import fetch_cartoon_background

    raw = fetch_cartoon_background(event_name)
    if not raw:
        return
    path = save_generated_background(slug, raw)
    if path:
        log.info("Stored Pollinations OG background for %s at %s", slug, path)
