import logging
import os
import sys
import threading
import time
from datetime import datetime

import uvicorn
from dotenv import load_dotenv

from camera import Camera
from config import load_settings, get_settings
from esp32 import ESP32
from image_processor import process_image
from printer import print_image
from storage import Storage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-8s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _run_web() -> None:
    port = int(os.getenv("WEB_PORT", "8080"))
    uvicorn.run("web.app:app", host="0.0.0.0", port=port, log_level="warning")


def _build_caption() -> str | None:
    s = get_settings().caption
    if not s.enabled:
        return None
    parts = []
    if s.show_date:
        parts.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
    if s.location:
        parts.append(s.location)
    return "  ".join(parts) if parts else None


def main() -> None:
    settings = load_settings()
    hw = settings.hardware

    threading.Thread(target=_run_web, daemon=True, name="web").start()
    logger.info("Web UI started on port %s", os.getenv("WEB_PORT", "8080"))

    camera  = Camera(device=hw.camera_device)
    esp32   = ESP32(port=hw.serial_port)
    storage = Storage(base_path=hw.storage_path)

    camera.open()
    esp32.open()
    esp32.wait_for_ready()
    esp32.send("IDLE")

    logger.info("Photobooth ready")

    while True:
        try:
            # ── IDLE ─────────────────────────────────────────────
            logger.info("Waiting for button press")
            esp32.wait_for_btn_press()

            # ── COUNTDOWN ────────────────────────────────────────
            logger.info("Countdown started")
            esp32.send("COUNTDOWN")
            time.sleep(3.0)

            # ── FLASH + CAPTURE ───────────────────────────────────
            esp32.send("FLASH")
            time.sleep(0.1)          # let ring reach full brightness
            raw_image = camera.capture()
            logger.info("Photo captured")

            # ── PROCESS ──────────────────────────────────────────
            esp32.send("PRINTING")
            current_settings = get_settings()   # picks up any live web UI changes
            print_img = process_image(raw_image, current_settings)

            # ── SAVE ─────────────────────────────────────────────
            storage.save_pair(raw_image, print_img)

            # ── PRINT ─────────────────────────────────────────────
            print_image(print_img, caption=_build_caption())

            # ── DONE ─────────────────────────────────────────────
            esp32.send("DONE")
            time.sleep(1.5)          # wait for DONE animation to finish
            esp32.send("IDLE")

        except KeyboardInterrupt:
            logger.info("Shutting down")
            esp32.send("ERROR")
            break

        except Exception as exc:
            logger.error("Error in main loop: %s", exc, exc_info=True)
            esp32.send("ERROR")
            time.sleep(3.0)
            esp32.send("IDLE")

    camera.close()
    esp32.close()


if __name__ == "__main__":
    main()
