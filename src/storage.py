import logging
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Delete oldest day folders until free space is above this threshold
_MIN_FREE_GB = 25.0


class Storage:
    def __init__(self, base_path: str = "photos"):
        self.base = Path(base_path)

    def save_pair(self, raw: Image.Image, processed: Image.Image) -> tuple[Path, Path]:
        now = datetime.now()
        day_dir = self.base / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        stem = now.strftime("%H%M%S")
        raw_path   = day_dir / f"{stem}_raw.jpg"
        print_path = day_dir / f"{stem}_print.png"

        raw.save(raw_path, "JPEG", quality=95)
        processed.save(print_path, "PNG")

        logger.info("Saved raw → %s", raw_path)
        logger.info("Saved print → %s", print_path)

        return raw_path, print_path

    def cleanup(self) -> None:
        """Delete oldest day folders until free disk space exceeds _MIN_FREE_GB."""
        while True:
            free_gb = shutil.disk_usage(self.base).free / 1e9
            if free_gb >= _MIN_FREE_GB:
                break

            # Oldest folder = smallest date name (YYYY-MM-DD sorts lexicographically)
            day_dirs = sorted(
                d for d in self.base.iterdir() if d.is_dir()
            )
            if not day_dirs:
                logger.warning("Disk low (%.1f Go libres) but no folders to delete", free_gb)
                break

            oldest = day_dirs[0]
            shutil.rmtree(oldest)
            logger.warning("Disk low — deleted %s (%.1f Go libres)", oldest.name, free_gb)
