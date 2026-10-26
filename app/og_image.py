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


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines[:3]


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


def render_event_og_png(event_name: str) -> bytes:
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

    name = (event_name or "Мероприятие").strip() or "Мероприятие"
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
    composed = composed.filter(ImageFilter.UnsharpMask(radius=1.1, percent=105, threshold=2))

    buf = BytesIO()
    composed.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
