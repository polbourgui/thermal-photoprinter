import logging
import time

import serial

logger = logging.getLogger(__name__)

# Opening a serial port resets the ESP32 (DTR signal).
# This delay lets it fully boot before we expect READY.
_BOOT_DELAY = 2.5


class ESP32:
    def __init__(self, port: str = "/dev/ttyACM0", baud: int = 115200):
        self.port = port
        self.baud = baud
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        self._ser = serial.Serial(self.port, self.baud, timeout=0.1)
        logger.info("Serial opened: %s @ %d", self.port, self.baud)
        time.sleep(_BOOT_DELAY)

    def send(self, command: str) -> None:
        if self._ser is None:
            raise RuntimeError("Serial port not opened")
        self._ser.write(f"{command}\n".encode())
        self._ser.flush()
        logger.debug("→ ESP32: %s", command)

    def _readline(self) -> str | None:
        if self._ser is None:
            return None
        raw = self._ser.readline()
        if not raw:
            return None
        line = raw.decode("utf-8", errors="ignore").strip()
        if line:
            logger.debug("← ESP32: %s", line)
        return line or None

    def wait_for_ready(self, timeout: float = 5.0) -> None:
        logger.info("Waiting for ESP8266 READY (timeout=%ss)…", timeout)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self._readline()
            if line == "READY":
                logger.info("ESP8266 ready")
                return
        logger.warning("READY not received — ESP8266 already running, continuing")

    def apply_led_config(self, num_leds: int) -> None:
        """Send LED count and safe brightness cap computed from USB current budget."""
        # 500 mA USB − 80 mA ESP board = 420 mA available for the strip.
        # Full-white WS2812B draws up to 60 mA per LED (20 mA/channel × 3).
        max_brightness = min(255, (420 * 255) // max(1, num_leds * 60))
        self.send(f"LEDS:{num_leds}")
        self.send(f"BRIGHT:{max_brightness}")
        peak_ma = num_leds * 60 * max_brightness // 255
        logger.info(
            "LED config: %d LEDs, brightness cap %d/255 (~%d mA peak)",
            num_leds, max_brightness, peak_ma,
        )

    def wait_for_btn_press(self) -> None:
        while True:
            line = self._readline()
            if line == "BTN_PRESS":
                return

    def close(self) -> None:
        if self._ser:
            self._ser.close()
            self._ser = None
