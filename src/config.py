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
class LayoutSettings:
    margin_top: int = 12
    margin_bottom: int = 24
    margin_sides: int = 8
    header_padding: int = 8        # px between header and photo
    footer_padding: int = 10       # px between photo and footer
    logo_font_size: int = 34       # "PROOF" logotype
    proof_font_size: int = 18      # "preuve n° XXX"
    footer_font_size: int = 20     # venue / artist / date / time
    separator: bool = False        # lines between header, photo, footer
    font_logo: str = ""            # filename in fonts/ dir (empty = system default)
    font_body: str = ""            # filename in fonts/ dir (empty = system default)


@dataclass
class ShotgunSettings:
    enabled: bool = False
    organizer_id: str = ""
    refresh_interval_minutes: int = 30


@dataclass
class HardwareSettings:
    camera_device: int = 0
    serial_port: str = "/dev/ttyUSB0"
    storage_path: str = "photos"
    num_leds: int = 111


@dataclass
class Settings:
    image: ImageSettings = field(default_factory=ImageSettings)
    caption: CaptionSettings = field(default_factory=CaptionSettings)
    printer: PrinterSettings = field(default_factory=PrinterSettings)
    hardware: HardwareSettings = field(default_factory=HardwareSettings)
    shotgun: ShotgunSettings = field(default_factory=ShotgunSettings)
    layout: LayoutSettings = field(default_factory=LayoutSettings)


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
            layout=LayoutSettings(**data.get("layout", {})),
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
