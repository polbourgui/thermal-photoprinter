import logging
import os
import time
from PIL import Image

from config import get_settings

logger = logging.getLogger(__name__)


def _detach_kernel_driver(vendor_id: int, product_id: int) -> None:
    """Detach usblp from the printer so escpos can call set_configuration().

    Order matters:
    1. pyusb detach — removes usblp's claim on each interface (module still loaded).
    2. dispose_resources — releases our libusb handle.
    3. modprobe -r usblp — NOW safe to unload (no device claiming it anymore).

    Without step 3, usblp could re-bind between dispose and escpos's set_configuration().
    """
    import shutil
    import subprocess
    import usb.core
    import usb.util

    # Step 1 — pyusb interface-level detach (module still loaded, just unclaimed)
    dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
    if dev is not None:
        try:
            cfg = dev.get_active_configuration()
            for intf in cfg:
                n = intf.bInterfaceNumber
                try:
                    if dev.is_kernel_driver_active(n):
                        dev.detach_kernel_driver(n)
                        logger.debug("Detached kernel driver from interface %d", n)
                except Exception as exc:
                    logger.debug("Interface %d detach: %s", n, exc)
        except Exception as exc:
            logger.debug("Driver detach: %s", exc)
        finally:
            # Step 2 — release our handle before calling modprobe
            usb.util.dispose_resources(dev)

    # Step 3 — unload the module (safe now that no interface claims it).
    # Use the modprobe SYMLINK, not realpath: sudo resolves to realpath for
    # sudoers matching (/usr/bin/kmod), but executes via the symlink so kmod
    # runs in modprobe-compatibility mode (kmod -r is invalid; modprobe -r works).
    modprobe = shutil.which("modprobe") or "/usr/sbin/modprobe"
    result = subprocess.run(["sudo", modprobe, "-r", "usblp"],
                            capture_output=True, timeout=5)
    if result.returncode != 0:
        logger.debug("modprobe -r usblp: %s", result.stderr.decode().strip())


def _get_printer():
    import escpos.printer
    vendor_id  = int(os.getenv("PRINTER_VENDOR_ID",  "0x04b8"), 16)
    product_id = int(os.getenv("PRINTER_PRODUCT_ID", "0x0e20"), 16)
    profile    = os.getenv("PRINTER_PROFILE", "default")
    _detach_kernel_driver(vendor_id, product_id)
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


