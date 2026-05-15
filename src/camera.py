import logging
import subprocess
import time

import cv2
from PIL import Image

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self, device: int = 0):
        self.device = device
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera /dev/video{self.device}")
        # Keep only the most recent frame in the driver buffer
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._disable_auto_exposure()
        logger.info("Camera opened: /dev/video%d", self.device)

    def _disable_auto_exposure(self) -> None:
        # auto_exposure=1 means manual on most V4L2 drivers (3 = auto)
        try:
            subprocess.run(
                ["v4l2-ctl", f"--device=/dev/video{self.device}",
                 "--set-ctrl=auto_exposure=1"],
                check=True, capture_output=True,
            )
            logger.info("Auto-exposure disabled")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("v4l2-ctl unavailable — auto-exposure not disabled")

    def capture(self) -> Image.Image:
        if self._cap is None:
            raise RuntimeError("Camera not opened")
        # Flush buffered frames: grab() decodes nothing, just advances the pointer
        deadline = time.monotonic() + 0.08
        while time.monotonic() < deadline:
            self._cap.grab()
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("Camera capture failed")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None
