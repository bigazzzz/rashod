from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

WIDTH = 1200
HEIGHT = 630
BG_PATH = Path(__file__).parent / "static" / "og-bg.jpg"

_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
)


@lru_cache(maxsize=1)
def _load_background() -> Image.Image:
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

    # (token, glue_to_previous) — glue=True for mid-word character chunks (no space).
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


@lru_cache(maxsize=256)
def render_event_og_jpeg(event_name: str) -> bytes:
    buf = BytesIO()
    _compose(event_name).save(buf, format="JPEG", quality=85, optimize=True, progressive=True)
    return buf.getvalue()


def _compose(event_name: str) -> Image.Image:
    base = _load_background().copy().convert("RGBA")
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Left-to-right vignette: keep the fire visible on the right, text readable on the left/center
    for x in range(WIDTH):
        t = x / (WIDTH - 1)
        alpha = int(150 * (1 - t) ** 1.35 + 55)
        draw.line([(x, 0), (x, HEIGHT)], fill=(6, 8, 18, alpha))

    # Soft bottom fade
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
