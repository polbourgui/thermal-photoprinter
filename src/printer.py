import logging
import os
from PIL import Image

from config import get_settings

logger = logging.getLogger(__name__)


def _get_printer():
    import escpos.printer
    vendor_id  = int(os.getenv("PRINTER_VENDOR_ID",  "0x04b8"), 16)
    product_id = int(os.getenv("PRINTER_PRODUCT_ID", "0x0e20"), 16)  # TM-m30 Bluetooth/USB
    profile    = os.getenv("PRINTER_PROFILE", "default")
    return escpos.printer.Usb(vendor_id, product_id, profile=profile)


def get_status() -> dict:
    """
    Query TM-M30 real-time sensors via DLE EOT.
    Returns a dict ready for /healthz. Never raises — errors become status fields.
    """
    try:
        p = _get_printer()
        try:
            raw = p.get_printer_status()
        finally:
            p.close()

        paper = raw.get("paper", {})
        error = raw.get("error", {})
        return {
            "online":         raw.get("ready", {}).get("status", False),
            "paper_present":  paper.get("paperPresent", None),
            "paper_near_end": paper.get("paperNearEnd", False),
            "paper_end":      paper.get("paperEnd", False),
            "cover_open":     paper.get("paperRecoverableError", False),
            "error_fatal":    error.get("Fatal", False),
            "error_recover":  error.get("Recoverable", False),
            "ok": (
                not paper.get("paperEnd", True)
                and not error.get("Fatal", True)
                and not paper.get("paperRecoverableError", True)
            ),
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
        p.image(ticket)
        p.cut()
        logger.info("Printed ticket (%dx%d px)", ticket.width, ticket.height)
    finally:
        p.close()

