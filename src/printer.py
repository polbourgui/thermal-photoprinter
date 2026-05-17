import logging
import os
import time
from PIL import Image

from config import get_settings

logger = logging.getLogger(__name__)

# ESC/POS base class provides image(), cut(), set(), _raw(), etc.
# The transport (USB read/write) is our own — escpos.printer.Usb is bypassed
# entirely because its open() calls set_configuration() without first claiming
# the interface, leaving a race window where usblp re-attaches.
try:
    from escpos.escpos import Escpos as _EscposBase
except ImportError:
    from escpos import Escpos as _EscposBase  # type: ignore


class _UsbPrinter(_EscposBase):
    """ESC/POS over a pyusb device handle we opened and claimed ourselves."""

    def open(self) -> None:
        # escpos >= 3.1: Escpos.__init__ calls self.open().  We suppress it
        # here; our device is injected after super().__init__() returns.
        pass

    def __init__(self, dev, in_ep: int, out_ep: int, profile: str = "default"):
        super().__init__(profile=profile)  # calls self.open() → pass
        self.device = dev
        self.in_ep  = in_ep
        self.out_ep = out_ep

    def _raw(self, msg: bytes) -> None:
        self.device.write(self.out_ep, msg)

    def close(self) -> None:
        import usb.util
        try:
            usb.util.release_interface(self.device, 0)
        except Exception:
            pass
        try:
            self.device.attach_kernel_driver(0)
        except Exception:
            pass
        try:
            usb.util.dispose_resources(self.device)
        except Exception:
            pass


def _get_printer() -> _UsbPrinter:
    import usb.core
    import usb.util

    vendor_id  = int(os.getenv("PRINTER_VENDOR_ID",  "0x04b8"), 16)
    product_id = int(os.getenv("PRINTER_PRODUCT_ID", "0x0e20"), 16)
    profile    = os.getenv("PRINTER_PROFILE", "default")

    dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
    if dev is None:
        raise RuntimeError(f"Printer {vendor_id:04x}:{product_id:04x} not found")

    # Enable auto-detach: claim_interface() will atomically detach any kernel
    # driver (usblp) without a race window.
    try:
        dev.set_auto_detach_kernel_driver(True)
    except Exception:
        pass

    # Manual pre-detach as belt-and-suspenders.
    for n in range(5):
        try:
            if dev.is_kernel_driver_active(n):
                dev.detach_kernel_driver(n)
                logger.debug("Detached kernel driver from interface %d", n)
        except Exception as exc:
            logger.debug("Interface %d: %s", n, exc)

    # set_configuration() fails with EBUSY when usblp or another driver still
    # holds the device — but the device is already in config 1, so we can skip
    # it safely.  claim_interface() below is what actually matters.
    try:
        dev.set_configuration()
    except usb.core.USBError as exc:
        if exc.errno == 16:
            logger.debug("set_configuration EBUSY — device already configured, skipping")
        else:
            raise

    # Claim interface 0.  With auto_detach this atomically removes usblp if it
    # re-attached between the manual detach and this call.  While the claim is
    # held, no kernel driver can re-attach — the race window is closed.
    usb.util.claim_interface(dev, 0)

    # Discover bulk endpoints on interface (0, alt-setting 0).
    cfg  = dev.get_active_configuration()
    intf = cfg[(0, 0)]
    out_ep = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: (
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
        ),
    )
    in_ep = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: (
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
        ),
    )

    in_addr  = in_ep.bEndpointAddress  if in_ep  else 0x82
    out_addr = out_ep.bEndpointAddress if out_ep else 0x01
    logger.debug("Printer claimed: in=0x%02x out=0x%02x", in_addr, out_addr)

    return _UsbPrinter(dev, in_addr, out_addr, profile=profile)


def get_status() -> dict:
    """Query TM-M30 sensors via ESC/POS DLE EOT (real-time status)."""
    try:
        p = _get_printer()
        try:
            try:
                p.device.read(p.in_ep, 64, timeout=100)
            except Exception:
                pass

            results = []
            for n in (1, 2, 3, 4):
                p._raw(bytes([0x10, 0x04, n]))
                time.sleep(0.05)
                data = p.device.read(p.in_ep, 16, timeout=300)
                results.append(data[0] if data else 0)
        finally:
            p.close()

        s1, s2, s3, s4 = results
        cover_open     = bool(s2 & 0x04)
        paper_end      = bool(s2 & 0x20) or bool(s4 & 0x60)
        paper_near_end = bool(s4 & 0x0C)
        error_fatal    = bool(s3 & 0x60)
        error_recover  = bool(s3 & 0x08)

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
