import logging
import os
from PIL import Image

from config import get_settings

logger = logging.getLogger(__name__)


def _get_printer():
    import escpos.printer
    vendor_id = int(os.getenv("PRINTER_VENDOR_ID", "0x04b8"), 16)
    product_id = int(os.getenv("PRINTER_PRODUCT_ID", "0x0e20"), 16)
    profile = os.getenv("PRINTER_PROFILE", "TM-P80")
    return escpos.printer.Usb(vendor_id, product_id, profile=profile)


def print_image(img: Image.Image, caption: str | None = None) -> None:
    settings = get_settings()
    p = _get_printer()
    p.set(align=settings.printer.align)
    p.image(img)
    if caption:
        p.text(caption)
    p.cut()
    logger.info("Printed successfully (caption=%s)", bool(caption))
