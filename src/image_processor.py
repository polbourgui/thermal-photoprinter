import logging
import numpy as np
from PIL import Image, ImageEnhance
from PIL.ExifTags import TAGS
from io import BytesIO

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


def _apply_dithering(img: Image.Image, algorithm: str) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape

    if algorithm == "threshold":
        result = np.where(arr > 128, 255, 0)

    elif algorithm in ("bayer4x4", "bayer8x8"):
        matrix = BAYER_4x4 if algorithm == "bayer4x4" else BAYER_8x8
        size = matrix.shape[0]
        tiled = np.tile(matrix, (h // size + 1, w // size + 1))[:h, :w]
        result = np.where(arr > tiled, 255, 0)

    elif algorithm == "floyd_steinberg":
        return img.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")

    else:
        logger.warning("Unknown dither algorithm '%s', falling back to bayer8x8", algorithm)
        return _apply_dithering(img, "bayer8x8")

    return Image.fromarray(result.astype(np.uint8))


def process_image(image_bytes: bytes, settings: Settings) -> Image.Image:
    img = Image.open(BytesIO(image_bytes))
    logger.info("Loaded image: %s %s", img.size, img.mode)

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

    # Apply enhancements before converting to grayscale
    img = ImageEnhance.Contrast(img).enhance(settings.image.contrast)
    img = ImageEnhance.Brightness(img).enhance(settings.image.brightness)
    img = ImageEnhance.Sharpness(img).enhance(settings.image.sharpness)

    # Convert to grayscale then apply dithering
    img = img.convert("L")
    img = _apply_dithering(img, settings.image.dither_algorithm)
    logger.info("Dithering applied: %s", settings.image.dither_algorithm)

    return img
