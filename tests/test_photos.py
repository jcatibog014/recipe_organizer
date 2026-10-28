import io

import pytest
from PIL import Image

from sangkap.photos import PhotoError, process


def make(size, fmt="JPEG", mode="RGB", exif=None):
    out = io.BytesIO()
    image = Image.new(mode, size, (255, 224, 122) if mode == "RGB" else None)
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(out, fmt, **kwargs)
    return out.getvalue()


def test_big_photo_is_shrunk_to_webp():
    data, width, height = process(make((4000, 3000)))
    assert (width, height) == (1000, 750)
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "WEBP"


def test_small_photo_keeps_its_size():
    assert process(make((300, 200), "PNG"))[1:] == (300, 200)


def test_transparent_png_is_fine():
    assert process(make((50, 50), "PNG", mode="RGBA"))[1:] == (50, 50)


def test_location_data_is_dropped():
    exif = Image.Exif()
    exif[0x8825] = {2: (14.0, 35.0, 0.0)}  # GPS info
    exif[0x0112] = 6  # "turn me": the phone held sideways
    data, width, height = process(make((400, 200), exif=exif))
    assert (width, height) == (200, 400)  # turned the right way up
    with Image.open(io.BytesIO(data)) as image:
        assert not image.getexif().get(0x8825)


@pytest.mark.parametrize("raw", [b"", b"hello", make((10, 10), "BMP")])
def test_not_a_usable_photo(raw):
    with pytest.raises(PhotoError):
        process(raw)


def test_decompression_bomb_is_refused(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(PhotoError, match="too big"):
        process(make((100, 100)))
