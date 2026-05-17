import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime

import uvicorn
from dotenv import load_dotenv

import state
import trigger as trig
from camera import Camera
from config import load_settings, get_settings
from counter import next_proof_number
from esp32 import ESP32
from image_processor import process_image
from layout import compose_ticket
from printer import print_ticket
from shotgun import ShotgunClient
from storage import Storage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-8s %(message)s",
    stream=sys.stdout,
    force=True,   # override any handlers added by uvicorn/other imports
)
# Suppress verbose internal messages from python-escpos
logging.getLogger("escpos").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _run_web() -> None:
    port = int(os.getenv("WEB_PORT", "8080"))
    uvicorn.run("web.app:app", host="0.0.0.0", port=port, log_level="warning")


_shotgun: ShotgunClient | None = None


def _get_event_info() -> tuple[str, str]:
    """Return (venue, artists) from Shotgun if active, else from manual settings."""
    if _shotgun is not None:
        event = _shotgun.get_current_event()
        if event:
            artists = "  •  ".join(event.artists[:2]) if event.artists else ""
            return event.venue_name, artists

    s = get_settings().caption
    return s.location, ""


def _printer_monitor(esp: ESP32) -> None:
    """
    Background thread: poll printer sensors every 5s.
    Requires 3 consecutive error reads before triggering ERROR (debounce).
    Clears immediately on a clean read.
    """
    from printer import get_status
    in_error      = False
    error_streak  = 0
    DEBOUNCE      = 3

    while True:
        time.sleep(5)
        try:
            s = get_status()
            printer_error = (
                s.get("paper_end")
                or s.get("cover_open")
                or s.get("error_fatal")
                or s.get("error_recover")
                or not s.get("ok", True)
            )
            if printer_error:
                error_streak += 1
                if error_streak >= DEBOUNCE and not in_error:
                    in_error = True
                    logger.warning("Printer error confirmed: %s", s)
                    esp.send("ERROR")
            else:
                error_streak = 0
                if in_error:
                    in_error = False
                    logger.info("Printer error cleared")
                    if trig._armed:
                        esp.send("IDLE")
        except Exception:
            pass


def _daily_cleanup(storage: Storage) -> None:
    """Background thread: run disk cleanup once per day at midnight."""
    while True:
        now = time.localtime()
        seconds_until_midnight = (
            (23 - now.tm_hour) * 3600
            + (59 - now.tm_min) * 60
            + (60 - now.tm_sec)
        )
        time.sleep(seconds_until_midnight)
        storage.cleanup()


def _serial_reader(esp: ESP32) -> None:
    """Background thread: relay BTN_PRESS from ESP8266 to the shared trigger."""
    while True:
        line = esp._readline()
        if line == "BTN_PRESS":
            fired = trig.fire()
            logger.info(
                "BTN_PRESS from ESP8266%s",
                "" if fired else " (ignored — shot in progress)",
            )
        elif line and line != "BTN_RELEASE":
            logger.debug("← ESP8266: %s", line)
        time.sleep(0.005)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Thermal photobooth")
    p.add_argument("--no-camera",  action="store_true", help="Skip camera (use gray placeholder)")
    p.add_argument("--no-printer", action="store_true", help="Skip printing (save only)")
    p.add_argument("--no-esp",     action="store_true", help="Skip ESP8266 (LEDs disabled)")
    return p.parse_args()


def main() -> None:
    args     = _parse_args()
    settings = load_settings()
    hw       = settings.hardware

    threading.Thread(target=_run_web, daemon=True, name="web").start()
    logger.info("Web UI started on port %s", os.getenv("WEB_PORT", "8080"))

    camera  = Camera(device=hw.camera_device) if not args.no_camera else None
    storage = Storage(base_path=hw.storage_path)

    esp: ESP32 | None = None
    if not args.no_esp:
        esp = ESP32(port=hw.serial_port)

    global _shotgun
    sg_cfg = settings.shotgun
    if sg_cfg.enabled and sg_cfg.organizer_id:
        _shotgun = ShotgunClient(organizer_id=sg_cfg.organizer_id)
        _shotgun.force_refresh()
        logger.info("Shotgun integration active (organizer: %s)", sg_cfg.organizer_id)
    else:
        logger.info("Shotgun integration disabled")

    if camera:
        camera.open()

    if esp:
        esp.open()
        state._esp = esp
        esp.wait_for_ready()
        esp.apply_led_config(hw.num_leds)
        esp.send("IDLE")
        threading.Thread(target=_serial_reader, args=(esp,), daemon=True, name="serial-reader").start()
    else:
        logger.warning("ESP8266 skipped — trigger via web UI (/trigger) or keyboard")

    if args.no_camera:
        logger.warning("Camera skipped — gray placeholder will be used")
    if args.no_printer:
        logger.warning("Printer skipped — tickets saved but not printed")

    threading.Thread(target=_daily_cleanup, args=(storage,), daemon=True, name="cleanup").start()
    if esp and not args.no_printer:
        threading.Thread(target=_printer_monitor, args=(esp,), daemon=True, name="printer-monitor").start()

    logger.info("Photobooth ready — waiting for trigger")
    trig.arm()

    while True:
        try:
            # ── IDLE ─────────────────────────────────────────────
            logger.info("Waiting for trigger (web UI /trigger or physical button)")
            trig.wait()
            trig.disarm()

            # ── COUNTDOWN ────────────────────────────────────────
            logger.info("Countdown started")
            if esp:
                esp.send("COUNTDOWN")
            time.sleep(3.0)

            # ── FLASH + CAPTURE ───────────────────────────────────
            # Timeline (firmware FLASH is now instantaneous, no fade):
            #   t=0      FLASH sent → ESP shows full white within 1 frame (~20ms)
            #   t=50ms   camera.capture() called
            #   t=50–90ms camera flushes stale frames (grab loop, ~2 frames @ 30fps)
            #   t=90ms   shutter reads fresh frame — LEDs at peak, 210ms of flash left
            if esp:
                esp.send("FLASH")
            time.sleep(0.05)

            if camera:
                raw_image = camera.capture()
                logger.info("Photo captured")
            else:
                from PIL import Image as _PILImage
                raw_image = _PILImage.new("RGB", (1200, 1600), (180, 180, 180))
                logger.info("Placeholder image used (no camera)")

            # ── PROCESS ──────────────────────────────────────────
            if esp:
                esp.send("PRINTING")
            current_settings = get_settings()
            print_img = process_image(raw_image, current_settings)

            # ── COMPOSE TICKET ────────────────────────────────────
            venue, artists = _get_event_info()
            proof_number   = next_proof_number()
            ticket = compose_ticket(
                print_img, venue, artists, proof_number, datetime.now(), current_settings
            )

            # ── SAVE ─────────────────────────────────────────────
            storage.save_pair(raw_image, ticket)

            # ── PRINT ─────────────────────────────────────────────
            if not args.no_printer:
                _t0 = time.monotonic()
                print_ticket(ticket)
                logger.info("PRINT_DURATION %.2fs", time.monotonic() - _t0)
            else:
                logger.info("Print skipped (--no-printer)")

            # ── DONE ─────────────────────────────────────────────
            if esp:
                esp.send("DONE")
            time.sleep(1.5)
            if esp:
                esp.send("IDLE")
            trig.arm()

        except KeyboardInterrupt:
            logger.info("Shutting down")
            if esp:
                esp.send("ERROR")
            break

        except Exception as exc:
            logger.error("Error in main loop: %s", exc, exc_info=True)
            if esp:
                esp.send("ERROR")
            trig.arm()
            time.sleep(3.0)
            if esp:
                esp.send("IDLE")

    if camera:
        camera.close()
    if esp:
        esp.close()


if __name__ == "__main__":
    main()
