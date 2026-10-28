"""Make an uploaded photo small and safe before it goes into the database.

A phone photo is 3-8 MB. We shrink it to at most 1000 px on the long side
and save it as WebP (about 50-120 KB), because the free database is small.
Saving a fresh copy also drops the EXIF data, which can hold the GPS
place where the photo was taken. Plain Python + Pillow (tests/test_photos.py).
"""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 1000
QUALITY = 80
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}  # MPO = some phone cameras' JPEG
# A "decompression bomb" is a tiny file that opens into a gigantic picture.
# Pillow refuses anything over this many pixels (about 50 megapixels).
Image.MAX_IMAGE_PIXELS = 50_000_000


class PhotoError(ValueError):
    """The upload isn't a photo we can use. The message is for the person."""


def process(raw):
    """Upload bytes -> (webp bytes, width, height). Raises PhotoError."""
    if not raw:
        raise PhotoError("Choose a photo first.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise PhotoError("Use a JPG, PNG, WebP or GIF photo.")
            image.load()
            # Phones save photos sideways plus a "turn me" note; apply it.
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            image.save(out, "WEBP", quality=QUALITY, method=4)
            return out.getvalue(), image.width, image.height
    except PhotoError:
        raise
    except Image.DecompressionBombError:
        raise PhotoError("That picture is too big. Try a smaller photo.") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise PhotoError("That file isn't a photo we can read.") from None
