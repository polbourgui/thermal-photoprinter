import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "config/settings.json"))


@dataclass
class ImageSettings:
    dither_algorithm: str = "bayer8x8"
    contrast: float = 1.0
    brightness: float = 1.0
    sharpness: float = 1.0
    auto_rotate: bool = True
    # Visual rendering
    grayscale_mode: str = "luminosity"   # luminosity | average | red | green | blue
    gamma: float = 1.0
    threshold: int = 128
    pre_blur: float = 0.0
    vignette: float = 0.0
    grain: float = 0.0
    posterize_bits: int = 0   # 0 = disabled, 1-7 = progressive posterization
    invert: bool = False


@dataclass
class CaptionSettings:
    enabled: bool = True
    location: str = "Home"
    show_date: bool = True


@dataclass
class PrinterSettings:
    max_width: int = 576
    align: str = "center"


@dataclass
class ShotgunSettings:
    enabled: bool = False
    organizer_id: str = ""
    refresh_interval_minutes: int = 30


@dataclass
class HardwareSettings:
    camera_device: int = 0
    serial_port: str = "/dev/ttyACM0"
    storage_path: str = "/photos"


@dataclass
class Settings:
    image: ImageSettings = field(default_factory=ImageSettings)
    caption: CaptionSettings = field(default_factory=CaptionSettings)
    printer: PrinterSettings = field(default_factory=PrinterSettings)
    hardware: HardwareSettings = field(default_factory=HardwareSettings)
    shotgun: ShotgunSettings = field(default_factory=ShotgunSettings)


_settings: Settings | None = None


def load_settings() -> Settings:
    global _settings
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        _settings = Settings(
            image=ImageSettings(**data.get("image", {})),
            caption=CaptionSettings(**data.get("caption", {})),
            printer=PrinterSettings(**data.get("printer", {})),
            hardware=HardwareSettings(**data.get("hardware", {})),
            shotgun=ShotgunSettings(**data.get("shotgun", {})),
        )
    else:
        _settings = Settings()
        save_settings(_settings)
    return _settings


def save_settings(settings: Settings) -> None:
    global _settings
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(asdict(settings), f, indent=2)
    _settings = settings


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        load_settings()
    return _settings
