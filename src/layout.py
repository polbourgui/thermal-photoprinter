"""
Ticket layout composer — fixed structure:

  ┌──────────────────────────────────────┐
  │  PROOF              preuve n° 001    │  header
  ├──────────────────────────────────────┤
  │           [ PHOTO portrait ]         │
  ├──────────────────────────────────────┤
  │  VENUE                  DD/MM/YYYY   │  footer line 1
  │  ARTISTS                    HH:MM    │  footer line 2
  └──────────────────────────────────────┘
"""

import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import Settings

logger = logging.getLogger(__name__)

_FONT_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]
_FONT_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _FONT_BOLD if bold else _FONT_REGULAR
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    if bold:
        # fallback: try regular
        return _load_font(size, bold=False)
    logger.warning("No TTF font found — using Pillow default")
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ── Header ────────────────────────────────────────────────────────────────────

def _render_header(width: int, proof_number: int, settings: Settings) -> Image.Image:
    lo = settings.layout
    logo_font  = _load_font(lo.logo_font_size, bold=True)
    proof_font = _load_font(lo.proof_font_size)

    pad_v = 10
    _, logo_h = _text_size(ImageDraw.Draw(Image.new("L", (1, 1))), "PROOF", logo_font)
    height = logo_h + pad_v * 2

    img  = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)

    # "PROOF" — left-aligned, vertically centred
    draw.text((lo.margin_sides, pad_v), "PROOF", fill=0, font=logo_font)

    # "preuve n° XXX" — right-aligned, vertically centred
    proof_text = f"preuve n° {proof_number:03d}"
    pw, ph = _text_size(draw, proof_text, proof_font)
    draw.text(
        (width - lo.margin_sides - pw, (height - ph) // 2),
        proof_text, fill=0, font=proof_font,
    )

    return img


# ── Footer ────────────────────────────────────────────────────────────────────

def _render_footer(
    width: int,
    venue: str,
    artists: str,
    captured_at: datetime,
    settings: Settings,
) -> Image.Image:
    lo   = settings.layout
    font = _load_font(lo.footer_font_size)

    dummy = ImageDraw.Draw(Image.new("L", (1, 1)))
    _, line_h = _text_size(dummy, "Ag", font)
    line_gap = int(line_h * 0.4)
    pad_v    = 8
    height   = pad_v + line_h + line_gap + line_h + pad_v

    img  = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)

    date_str  = captured_at.strftime("%d/%m/%Y")
    time_str  = captured_at.strftime("%H:%M")
    pad_h     = lo.margin_sides

    def draw_row(y: int, left: str, right: str) -> None:
        draw.text((pad_h, y), left.upper(), fill=0, font=font)
        rw, _ = _text_size(draw, right, font)
        draw.text((width - pad_h - rw, y), right, fill=0, font=font)

    draw_row(pad_v,                      venue,   date_str)
    draw_row(pad_v + line_h + line_gap,  artists, time_str)

    return img


# ── Ticket composer ───────────────────────────────────────────────────────────

def compose_ticket(
    photo: Image.Image,
    venue: str,
    artists: str,
    proof_number: int,
    captured_at: datetime,
    settings: Settings,
) -> Image.Image:
    """
    Compose the full printable ticket.
    `photo` must already be processed (dithered, grayscale).
    Returns a grayscale L-mode image.
    """
    lo    = settings.layout
    width = settings.printer.max_width

    # Scale photo to ticket width
    photo_w = width - lo.margin_sides * 2
    pw, ph  = photo.size
    photo   = photo.resize((photo_w, int(ph * (photo_w / pw))), Image.NEAREST)

    header  = _render_header(width, proof_number, settings)
    footer  = _render_footer(width, venue, artists, captured_at, settings)
    sep_h   = 1 if lo.separator else 0

    total_h = (
        lo.margin_top
        + header.height + lo.header_padding + sep_h
        + photo.height
        + sep_h + lo.footer_padding + footer.height
        + lo.margin_bottom
    )

    ticket = Image.new("L", (width, total_h), 255)
    draw   = ImageDraw.Draw(ticket)

    y = lo.margin_top
    ticket.paste(header, (0, y));              y += header.height + lo.header_padding
    if sep_h:
        draw.line([(0, y), (width, y)], fill=0, width=1); y += sep_h
    ticket.paste(photo, (lo.margin_sides, y)); y += photo.height
    if sep_h:
        draw.line([(0, y), (width, y)], fill=0, width=1); y += sep_h
    y += lo.footer_padding
    ticket.paste(footer, (0, y))

    return ticket


# ── Mockup (web UI) ───────────────────────────────────────────────────────────

def make_mockup(settings: Settings) -> Image.Image:
    """Ticket mockup with a portrait photo placeholder — for layout preview."""
    from counter import peek

    width   = settings.printer.max_width
    lo      = settings.layout
    photo_w = width - lo.margin_sides * 2
    photo_h = int(photo_w * 4 / 3)   # portrait 3:4

    placeholder = Image.new("L", (photo_w, photo_h), 215)
    draw = ImageDraw.Draw(placeholder)

    # Subtle grid
    step_x = photo_w // 4
    step_y = photo_h // 6
    for x in range(0, photo_w, step_x):
        draw.line([(x, 0), (x, photo_h)], fill=200, width=1)
    for y in range(0, photo_h, step_y):
        draw.line([(0, y), (photo_w, y)], fill=200, width=1)

    font = _load_font(settings.layout.footer_font_size)
    label = f"{photo_w} × {photo_h} px"
    dummy_draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    lw, lh = _text_size(dummy_draw, label, font)
    draw.text(((photo_w - lw) // 2, (photo_h - lh) // 2), label, fill=150, font=font)

    return compose_ticket(
        photo=placeholder,
        venue="LA CIGALE",
        artists="DJ SNAKE",
        proof_number=peek() + 1,
        captured_at=datetime.now(),
        settings=settings,
    )
