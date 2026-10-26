from PIL import Image, ImageDraw

from app.og_image import WIDTH, _load_font, _wrap_text, render_event_og_jpeg


def test_wrap_text_breaks_long_word_without_spaces():
    draw = ImageDraw.Draw(Image.new("RGB", (WIDTH, 100)))
    font = _load_font(68)
    max_width = WIDTH - 220
    long_word = "Супердлинноеназваниемероприятиябезпробеловвообще"
    assert draw.textlength(long_word, font=font) > max_width

    lines = _wrap_text(draw, long_word, font, max_width)
    assert len(lines) >= 2
    assert len(lines) <= 3
    for line in lines:
        assert draw.textlength(line, font=font) <= max_width + 1


def test_wrap_text_ellipsis_when_too_many_lines():
    draw = ImageDraw.Draw(Image.new("RGB", (WIDTH, 100)))
    font = _load_font(68)
    max_width = WIDTH - 220
    text = " ".join(["Слово"] * 40)
    lines = _wrap_text(draw, text, font, max_width, max_lines=3)
    assert len(lines) == 3
    assert lines[-1].endswith("…")


def test_render_og_accepts_long_title():
    jpeg = render_event_og_jpeg("Оченьдлинноеназваниесобытиябезпробеловдляпроверкипереноса")
    assert jpeg[:3] == b"\xff\xd8\xff"
    assert len(jpeg) > 10_000
