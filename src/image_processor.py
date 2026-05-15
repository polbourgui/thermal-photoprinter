import logging
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from PIL.ExifTags import TAGS

from config import Settings

logger = logging.getLogger(__name__)

# Bayer threshold matrices (normalized to 0-255)
BAYER_4x4 = (np.array([
    [ 0,  8,  2, 10],
    [12,  4, 14,  6],
    [ 3, 11,  1,  9],
    [15,  7, 13,  5],
]) / 16.0 * 255.0)

BAYER_8x8 = (np.array([
    [ 0, 48, 12, 60,  3, 51, 15, 63],
    [32, 16, 44, 28, 35, 19, 47, 31],
    [ 8, 56,  4, 52, 11, 59,  7, 55],
    [40, 24, 36, 20, 43, 27, 39, 23],
    [ 2, 50, 14, 62,  1, 49, 13, 61],
    [34, 18, 46, 30, 33, 17, 45, 29],
    [10, 58,  6, 54,  9, 57,  5, 53],
    [42, 26, 38, 22, 41, 25, 37, 21],
]) / 64.0 * 255.0)


def _fix_orientation(img: Image.Image) -> Image.Image:
    try:
        orientation_tag = next(
            tag_id for tag_id, name in TAGS.items() if name == "Orientation"
        )
        exif = img._getexif()
        if exif and orientation_tag in exif:
            orientation = exif[orientation_tag]
            rotations = {3: 180, 6: 270, 8: 90}
            if orientation in rotations:
                img = img.rotate(rotations[orientation], expand=True)
    except (AttributeError, KeyError, StopIteration):
        pass
    return img


def _convert_grayscale(img: Image.Image, mode: str) -> Image.Image:
    """Convert to grayscale using the requested channel/formula."""
    rgb = img.convert("RGB")
    if mode == "red":
        return rgb.split()[0]
    if mode == "green":
        return rgb.split()[1]
    if mode == "blue":
        return rgb.split()[2]
    if mode == "average":
        arr = np.array(rgb, dtype=np.float32).mean(axis=2)
        return Image.fromarray(arr.astype(np.uint8))
    # default: luminosity (ITU-R 601)
    return rgb.convert("L")


def _apply_gamma(arr: np.ndarray, gamma: float) -> np.ndarray:
    """Apply gamma correction. gamma < 1 lightens midtones, gamma > 1 darkens them."""
    corrected = np.power(arr / 255.0, gamma) * 255.0
    return np.clip(corrected, 0, 255).astype(np.uint8)


def _apply_vignette(arr: np.ndarray, strength: float) -> np.ndarray:
    """Darken edges with a radial gradient (analog/film look)."""
    h, w = arr.shape
    yv, xv = np.mgrid[-1:1:complex(0, h), -1:1:complex(0, w)]
    radius = np.sqrt(xv ** 2 + yv ** 2)
    radius /= radius.max()
    mask = np.clip(1.0 - strength * radius ** 1.5, 0.0, 1.0)
    return np.clip(arr * mask, 0, 255).astype(np.uint8)


def _apply_grain(arr: np.ndarray, strength: float) -> np.ndarray:
    """Add random film grain before dithering."""
    noise = np.random.normal(0, strength * 40, arr.shape)
    return np.clip(arr + noise, 0, 255).astype(np.uint8)


def _atkinson_dither(arr: np.ndarray) -> np.ndarray:
    """
    Atkinson dithering — distributes 1/8 of the error to 6 neighbours.
    Produces lighter, more detailed results than Floyd-Steinberg.
    """
    h, w = arr.shape
    buf = arr.astype(np.float32).copy()
    for y in range(h):
        for x in range(w):
            old = buf[y, x]
            new = 255.0 if old > 127.0 else 0.0
            buf[y, x] = new
            err = (old - new) / 8.0
            if err == 0.0:
                continue
            for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    buf[ny, nx] += err
    return np.clip(buf, 0, 255).astype(np.uint8)


def _apply_dithering(img: Image.Image, algorithm: str, threshold: int = 128) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape

    if algorithm == "threshold":
        result = np.where(arr > threshold, 255, 0)

    elif algorithm in ("bayer4x4", "bayer8x8"):
        matrix = BAYER_4x4 if algorithm == "bayer4x4" else BAYER_8x8
        size = matrix.shape[0]
        # Shift the Bayer matrix by the threshold offset so the user can bias
        # overall exposure without changing the dither pattern shape.
        offset = (threshold - 128) * (255.0 / 128.0)
        tiled = np.tile(matrix, (h // size + 1, w // size + 1))[:h, :w] + offset
        result = np.where(arr > tiled, 255, 0)

    elif algorithm == "floyd_steinberg":
        return img.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")

    elif algorithm == "atkinson":
        result = _atkinson_dither(arr)

    else:
        logger.warning("Unknown dither algorithm '%s', falling back to bayer8x8", algorithm)
        return _apply_dithering(img, "bayer8x8", threshold)

    return Image.fromarray(result.astype(np.uint8))


def process_image(img: Image.Image, settings: Settings) -> Image.Image:
    logger.info("Processing image: %s %s", img.size, img.mode)

    if settings.image.auto_rotate:
        img = _fix_orientation(img)

    # Resize to printer width
    max_width = settings.printer.max_width
    w, h = img.size
    if w > max_width:
        ratio = max_width / float(w)
        new_h = int(h * ratio)
        img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)
        logger.info("Resized to %sx%s", max_width, new_h)

    # Tone adjustments (still in colour so enhancements have full effect)
    img = ImageEnhance.Contrast(img).enhance(settings.image.contrast)
    img = ImageEnhance.Brightness(img).enhance(settings.image.brightness)
    img = ImageEnhance.Sharpness(img).enhance(settings.image.sharpness)

    # Pre-blur softens edges before dithering (dreamy / lo-fi look)
    if settings.image.pre_blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=settings.image.pre_blur))

    # Convert to grayscale using the chosen channel/formula
    img = _convert_grayscale(img, settings.image.grayscale_mode)

    # Posterize: reduce tonal levels (graphic / silkscreen look)
    if settings.image.posterize_bits > 0:
        bits = max(1, min(7, settings.image.posterize_bits))
        img = ImageOps.posterize(img, bits)

    # Gamma correction: compensate for thermal printer's tendency to print dark
    if settings.image.gamma != 1.0:
        arr = _apply_gamma(np.array(img, dtype=np.float32), settings.image.gamma)
        img = Image.fromarray(arr)

    # Vignette: darken edges
    if settings.image.vignette > 0:
        arr = _apply_vignette(np.array(img, dtype=np.float32), settings.image.vignette)
        img = Image.fromarray(arr)

    # Film grain: random noise before dithering
    if settings.image.grain > 0:
        arr = _apply_grain(np.array(img, dtype=np.float32), settings.image.grain)
        img = Image.fromarray(arr)

    # Dithering
    img = _apply_dithering(img, settings.image.dither_algorithm, settings.image.threshold)
    logger.info("Dithering applied: %s (threshold=%d)", settings.image.dither_algorithm, settings.image.threshold)

    # Invert: negative/white-on-black effect
    if settings.image.invert:
        img = ImageOps.invert(img)

    return img
