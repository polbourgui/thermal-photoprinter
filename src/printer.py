import logging
import os
import time
from PIL import Image

from config import get_settings

logger = logging.getLogger(__name__)


def _get_printer():
    import escpos.printer
    vendor_id  = int(os.getenv("PRINTER_VENDOR_ID",  "0x04b8"), 16)
    product_id = int(os.getenv("PRINTER_PRODUCT_ID", "0x0e20"), 16)
    profile    = os.getenv("PRINTER_PROFILE", "default")
    return escpos.printer.Usb(vendor_id, product_id, profile=profile)


def get_status() -> dict:
    """
    Query TM-M30 sensors via ESC/POS DLE EOT (real-time status).
    Works regardless of python-escpos version.
    """
    try:
        p = _get_printer()
        try:
            # Flush any stale data in the USB IN buffer
            try:
                p.device.read(p.in_ep, 64, timeout=100)
            except Exception:
                pass

            results = []
            for n in (1, 2, 3, 4):          # printer / offline / error / paper
                p._raw(bytes([0x10, 0x04, n]))
                time.sleep(0.05)
                data = p.device.read(p.in_ep, 16, timeout=300)
                results.append(data[0] if data else 0)
        finally:
            p.close()

        s1, s2, s3, s4 = results
        cover_open     = bool(s2 & 0x04)          # byte 2, bit 2
        paper_end      = bool(s2 & 0x20) or bool(s4 & 0x60)  # offline + paper sensor
        paper_near_end = bool(s4 & 0x0C)          # byte 4, bits 2-3
        error_fatal    = bool(s3 & 0x60)          # byte 3, bits 5-6
        error_recover  = bool(s3 & 0x08)          # byte 3, bit 3

        return {
            "online":         bool(s1 & 0x08),
            "paper_present":  not paper_end,
            "paper_near_end": paper_near_end,
            "paper_end":      paper_end,
            "cover_open":     cover_open,
            "error_fatal":    error_fatal,
            "error_recover":  error_recover,
            "ok": not (cover_open or paper_end or error_fatal),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def print_ticket(ticket: Image.Image) -> None:
    """Send a fully composed ticket image to the printer."""
    status = get_status()
    if not status.get("ok", False):
        raise RuntimeError(f"Printer not ready: {status}")

    settings = get_settings()
    p = _get_printer()
    try:
        p.set(align=settings.printer.align)
        p.image(ticket.rotate(180))
        p.cut()
        logger.info("Printed ticket (%dx%d px)", ticket.width, ticket.height)
    finally:
        p.close()


