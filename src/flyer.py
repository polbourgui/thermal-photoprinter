"""
Render the PROOF thermal flyer entirely with Pillow — no browser needed.

Layout mirrors assets/flyer.html:
  photo silhouette (full width)
  PROOF stamp block  /  tagline  /  body text
  props list  /  footer  /  proof ref
"""
import logging

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from layout import _load_font, _text_size

logger = logging.getLogger(__name__)

_PAD_H  = 24   # horizontal padding inside content area
_GAP    = 14   # standard vertical gap between blocks


# ── helpers ───────────────────────────────────────────────────────────────────

def _draw_dashed_line(draw: ImageDraw.ImageDraw, x0: int, y: int, x1: int,
                      dash: int = 6, gap: int = 4, fill: int = 180) -> None:
    x = x0
    while x < x1:
        draw.line([(x, y), (min(x + dash, x1), y)], fill=fill, width=1)
        x += dash + gap


def _stamp_block(draw: ImageDraw.ImageDraw, x: int, y: int,
                 text: str, font, border: int = 2) -> tuple[int, int]:
    """Draw a bordered stamp (like HTML .stamp). Returns (w, h)."""
    tw, th = _text_size(draw, text, font)
    pad_x, pad_y = 18, 5
    w = tw + pad_x * 2
    h = th + pad_y * 2
    draw.rectangle([x, y, x + w - 1, y + h - 1], outline=0, width=border)
    draw.text((x + pad_x, y + pad_y), text, fill=0, font=font)
    return w, h


# ── photo silhouette placeholder ──────────────────────────────────────────────

def _make_photo_zone(width: int, height: int) -> Image.Image:
    """Dithered silhouette: backlit figure, thermal aesthetic."""
    rng = np.random.default_rng(42)
    arr = np.full((height, width), 235, dtype=np.int16)

    # Darker flanks
    flank = width // 5
    for i in range(flank):
        v = int(45 * (1 - i / flank))
        arr[:, i]           -= v
        arr[:, width - 1 - i] -= v

    # Bottom edge darkening
    fade_h = height // 6
    for i in range(fade_h):
        v = int(25 * (1 - i / fade_h))
        arr[height - 1 - i, :] -= v

    # Head ellipse — dark
    cx, cy = width // 2, int(height * 0.36)
    rx, ry = int(width * 0.088), int(height * 0.13)
    ys, xs = np.ogrid[:height, :width]
    head_mask = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1.0
    arr[head_mask] = 35

    # Body rectangle — dark
    bx1, bx2 = int(width * 0.41), int(width * 0.59)
    by1      = int(height * 0.425)
    arr[by1:, bx1:bx2] = 35

    # Backlit halo — lighten area around head
    halo_rx, halo_ry = int(width * 0.27), int(height * 0.26)
    halo_dist = ((xs - cx) / halo_rx) ** 2 + ((ys - cy) / halo_ry) ** 2
    halo_mask = (halo_dist < 1.0) & (~head_mask)
    arr[halo_mask] = np.clip(
        arr[halo_mask] + (15 * (1 - halo_dist[halo_mask])).astype(np.int16),
        0, 255,
    )

    # Fine grain
    arr += rng.integers(-6, 7, arr.shape, dtype=np.int16)
    arr  = np.clip(arr, 0, 255).astype(np.uint8)

    # Thin border
    img  = Image.fromarray(arr, mode="L")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width - 1, height - 1],
                   outline=200, width=1)
    return img


# ── main renderer ─────────────────────────────────────────────────────────────

def render_flyer(print_width: int = 576) -> Image.Image:
    """Return a grayscale PIL Image of the PROOF flyer at print_width pixels."""

    W       = print_width
    PAD     = _PAD_H
    CW      = W - PAD * 2          # content width

    # Fonts
    f_stamp    = _load_font(int(W * 0.090), bold=True)   # "PROOF" big stamp
    f_tagline  = _load_font(int(W * 0.062), bold=True)   # "PREUVE DE…"
    f_sub      = _load_font(int(W * 0.026))              # subtitle body
    f_body     = _load_font(int(W * 0.023))              # props list
    f_footer   = _load_font(int(W * 0.023))              # footer lines
    f_url      = _load_font(int(W * 0.026))              # URL
    f_ref      = _load_font(int(W * 0.020))              # proof ref small
    f_sig      = _load_font(int(W * 0.032), bold=True)   # small PROOF sig

    # ── measure all blocks first so we can allocate total height ──────────────
    dummy_img  = Image.new("L", (W, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)

    def lh(font) -> int:
        _, h = _text_size(dummy_draw, "Ag", font)
        return h

    photo_h       = int(W * 0.75)    # 4:3-ish portrait

    stamp_lh      = lh(f_stamp)
    stamp_block_h = stamp_lh + 10 + _GAP + 1   # stamp + padding + sep line

    tagline_lines = ["PREUVE DE", "PRÉSENCE NOCTURNE"]
    tagline_lh    = lh(f_tagline)
    tagline_h     = len(tagline_lines) * tagline_lh + int(tagline_lh * 0.15) * (len(tagline_lines) - 1)

    sub_lines = [
        "Photomaton thermique autonome.",
        "Une photo en quelques secondes, imprimée",
        "sur papier. Pas d'application. Pas d'écran.",
    ]
    sub_lh = lh(f_sub)
    sub_h  = len(sub_lines) * sub_lh + 3 * (len(sub_lines) - 1)

    props = [
        "Impression instantanée, rendu argentique",
        "Zéro interaction numérique",
        "Caption personnalisée — lieu, date, heure",
        "Archive automatique pour votre communication",
        "Installation en moins de 30 minutes",
    ]
    body_lh  = lh(f_body)
    props_h  = len(props) * body_lh + 4 * (len(props) - 1)

    footer_lines = ["LOCATION · PARIS", "CLUBS · SOIRÉES · FESTIVALS · VERNISSAGES"]
    footer_lh    = lh(f_footer)
    url_lh       = lh(f_url)
    footer_h     = len(footer_lines) * footer_lh + 3 * (len(footer_lines) - 1) + 5 + url_lh

    ref_lh   = lh(f_ref)
    sig_lh   = lh(f_sig)
    ref_h    = max(ref_lh * 2 + 3, sig_lh + 6)

    total_h = (
        photo_h
        + _GAP + stamp_block_h
        + _GAP + tagline_h
        + _GAP + sub_h
        + _GAP + 1 + _GAP    # solid rule
        + props_h
        + _GAP + 1 + _GAP    # dashed rule
        + footer_h
        + _GAP * 2 + 1 + _GAP + ref_h   # proof ref with separator
        + _GAP * 2
    )

    # ── draw ─────────────────────────────────────────────────────────────────
    img  = Image.new("L", (W, total_h), 255)
    draw = ImageDraw.Draw(img)

    y = 0

    # Photo zone — full width, no padding
    photo = _make_photo_zone(W, photo_h)
    img.paste(photo, (0, 0))
    y += photo_h + _GAP

    # PROOF stamp block
    _, sh = _stamp_block(draw, PAD, y, "PROOF", f_stamp, border=2)
    y += sh + _GAP
    draw.line([(PAD, y), (W - PAD, y)], fill=0, width=1)
    y += 1 + _GAP

    # Tagline
    line_gap = int(tagline_lh * 0.15)
    for line in tagline_lines:
        draw.text((PAD, y), line, fill=0, font=f_tagline)
        y += tagline_lh + line_gap
    y += _GAP - line_gap

    # Subtitle
    for line in sub_lines:
        draw.text((PAD, y), line, fill=120, font=f_sub)
        y += sub_lh + 3
    y += _GAP

    # Solid rule
    draw.line([(PAD, y), (W - PAD, y)], fill=200, width=1)
    y += 1 + _GAP

    # Props list
    bullet_w, _ = _text_size(draw, "– ", f_body)
    for prop in props:
        draw.text((PAD, y), "–", fill=180, font=f_body)
        draw.text((PAD + bullet_w, y), prop, fill=0, font=f_body)
        y += body_lh + 4
    y += _GAP

    # Dashed rule
    _draw_dashed_line(draw, PAD, y, W - PAD)
    y += 1 + _GAP

    # Footer
    for line in footer_lines:
        draw.text((PAD, y), line, fill=160, font=f_footer)
        y += footer_lh + 3
    y += 5
    draw.text((PAD, y), "proof-paris.com", fill=80, font=f_url)
    y += url_lh + _GAP * 2

    # Proof ref separator
    draw.line([(PAD, y), (W - PAD, y)], fill=220, width=1)
    y += 1 + _GAP

    # Proof ref: left text + right mini stamp
    ref_text = ["CECI EST UNE PREUVE.", "IMPRIMÉE SUR PROOF."]
    for line in ref_text:
        draw.text((PAD, y), line, fill=180, font=f_ref)
        y += ref_lh + 3

    sig_w, sig_h = _stamp_block(
        draw,
        W - PAD - int(CW * 0.28),
        y - ref_lh * 2 - 6 + (ref_h - sig_h) // 2 if (sig_h := lh(f_sig) + 10) else y,
        "PROOF", f_sig, border=1,
    )

    y += _GAP * 2

    logger.info("Flyer rendered: %dx%d px", W, total_h)
    return img.crop((0, 0, W, y))
