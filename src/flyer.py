"""Render assets/flyer.html to a PIL Image ready for print_ticket()."""
import io
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

FLYER_HTML = Path(__file__).parent.parent / "assets" / "flyer.html"

# 576px = full printable width on Epson TM-M30 at 8 dots/mm (80mm paper)
_PRINT_WIDTH = 576


def render_flyer(print_width: int = _PRINT_WIDTH) -> Image.Image:
    """
    Launch a headless Chromium browser, screenshot the .receipt element,
    and return a PIL Image scaled to print_width pixels wide.

    Requires:  pip install playwright && playwright install --with-deps chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed — run:\n"
            "  pip install playwright\n"
            "  playwright install --with-deps chromium"
        )

    url = FLYER_HTML.resolve().as_uri()
    logger.info("Rendering flyer: %s", url)

    with sync_playwright() as p:
        # device_scale_factor ≈ 1.8 so receipt (320 CSS px) → ~576 px raw
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 320, "height": 1200},
            device_scale_factor=1.8,
        )
        page.goto(url, timeout=10_000)
        try:
            # Wait for web fonts; skip gracefully on offline setups
            page.wait_for_load_state("networkidle", timeout=4_000)
        except Exception:
            pass

        receipt = page.locator(".receipt")
        png_bytes = receipt.screenshot(type="png")
        browser.close()

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    logger.info("Raw screenshot: %dx%d px", img.width, img.height)

    # Scale to exact printer width
    if img.width != print_width:
        h = int(img.height * print_width / img.width)
        img = img.resize((print_width, h), Image.LANCZOS)
        logger.info("Resized to %dx%d px", img.width, img.height)

    return img
