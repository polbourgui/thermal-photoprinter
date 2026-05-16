"""
Ticket layout composer.

Takes a processed (dithered) photo and an optional caption string,
returns a single PIL image representing the full printed ticket.

Also exposes make_mockup() which renders the same layout with a
placeholder photo — used by the web UI to visualise layout settings
without needing a real capture.
"""

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import Settings

logger = logging.getLogger(__name__)

# Candidate system font paths, tried in order
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    logger.warning("No TTF font found — using Pillow default (small bitmap font)")
    return ImageFont.load_default()


def _render_caption_strip(text: str, width: int, font_size: int) -> Image.Image:
    """Render caption text centred on a white strip, auto-wrapping long lines."""
    font = _load_font(font_size)
    line_spacing = int(font_size * 0.35)

    lines = text.strip().splitlines()
    if not lines:
        return Image.new("L", (width, 0), 255)

    # Measure each line height
    dummy = Image.new("L", (1, 1))
    draw = ImageDraw.Draw(dummy)
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])

    total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    strip = Image.new("L", (width, total_height + font_size // 2), 255)
    draw = ImageDraw.Draw(strip)

    y = font_size // 4
    for line, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        draw.text((x, y), line, fill=0, font=font)
        y += lh + line_spacing

    return strip


def compose_ticket(photo: Image.Image, caption: str | None, settings: Settings) -> Image.Image:
    """
    Compose the final printable ticket from a processed photo and caption.
    Returns a grayscale L-mode image.
    """
    lo = settings.layout
    width = settings.printer.max_width

    # Fit photo to ticket width (preserve aspect ratio)
    pw, ph = photo.size
    if pw != width - lo.margin_sides * 2:
        target_w = width - lo.margin_sides * 2
        scale = target_w / pw
        photo = photo.resize((target_w, int(ph * scale)), Image.NEAREST)

    # Caption strip
    caption_strip: Image.Image | None = None
    if caption and lo.caption_position != "none":
        caption_strip = _render_caption_strip(caption, width, lo.caption_font_size)

    # Separator line (1px)
    separator_h = 2 if lo.separator and caption_strip else 0

    # Total height
    total_h = lo.margin_top + photo.height
    if caption_strip:
        total_h += lo.caption_padding + separator_h + caption_strip.height
    total_h += lo.margin_bottom

    ticket = Image.new("L", (width, total_h), 255)

    def paste(img: Image.Image, y: int) -> int:
        ticket.paste(img, (lo.margin_sides, y))
        return y + img.height

    y = lo.margin_top

    if caption_strip and lo.caption_position == "top":
        y = paste(caption_strip, y)
        y += lo.caption_padding
        if lo.separator:
            ImageDraw.Draw(ticket).line([(0, y), (width, y)], fill=180, width=1)
            y += separator_h

    y = paste(photo, y)

    if caption_strip and lo.caption_position == "bottom":
        y += lo.caption_padding
        if lo.separator:
            ImageDraw.Draw(ticket).line([(0, y), (width, y)], fill=180, width=1)
            y += separator_h
        paste(caption_strip, y)

    return ticket


# ── Mockup (for web UI) ────────────────────────────────────────────────────────

_SAMPLE_CAPTION = "CROSSROADS\nDJ SNAKE\n20/01/2025  23:47"


def make_mockup(settings: Settings) -> Image.Image:
    """
    Generate a ticket mockup with a placeholder photo rectangle.
    The photo placeholder height is proportional to a 4:3 landscape crop
    at the configured print width.
    """
    width = settings.printer.max_width
    lo = settings.layout

    photo_w = width - lo.margin_sides * 2
    photo_h = int(photo_w * 3 / 4)

    # Placeholder: mid-gray rectangle with subtle "PHOTO" label
    placeholder = Image.new("L", (photo_w, photo_h), 210)
    draw = ImageDraw.Draw(placeholder)

    # Grid lines for scale reference
    step = photo_w // 6
    for x in range(0, photo_w, step):
        draw.line([(x, 0), (x, photo_h)], fill=195, width=1)
    step_h = photo_h // 4
    for y_line in range(0, photo_h, step_h):
        draw.line([(0, y_line), (photo_w, y_line)], fill=195, width=1)

    # "PHOTO" label centred
    font = _load_font(settings.layout.caption_font_size + 4)
    label = f"PHOTO  {photo_w} × {photo_h} px"
    bbox = draw.textbbox((0, 0), label, font=font)
    lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((photo_w - lw) // 2, (photo_h - lh) // 2),
        label, fill=150, font=font,
    )

    caption_text = _SAMPLE_CAPTION if settings.caption.enabled else None
    return compose_ticket(placeholder, caption_text, settings)
