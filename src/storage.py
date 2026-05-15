import logging
from datetime import datetime
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, base_path: str = "/photos"):
        self.base = Path(base_path)

    def save_pair(self, raw: Image.Image, processed: Image.Image) -> tuple[Path, Path]:
        now = datetime.now()
        day_dir = self.base / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        stem = now.strftime("%H%M%S")
        raw_path  = day_dir / f"{stem}_raw.jpg"
        # PNG for processed: lossless, important for dithered B&W analysis
        print_path = day_dir / f"{stem}_print.png"

        raw.save(raw_path, "JPEG", quality=95)
        processed.save(print_path, "PNG")

        logger.info("Saved raw → %s", raw_path)
        logger.info("Saved print → %s", print_path)
        return raw_path, print_path
