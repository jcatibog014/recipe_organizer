"""Turn your AI-made kawaii picture into the app's background tile.

1. Make the picture with the prompt in docs/ART_PROMPTS.md.
2. Save it as docs/art_src/background.png (or .jpg / .webp).
3. Run:   .venv\\Scripts\\python docs\\make_background.py
4. Restart the app: the emoji pattern is replaced by your picture.

What it does (with Pillow, no internet):
- If the picture has no see-through background (a JPG on white, say), it
  makes the plain light background see-through, starting from the corners.
- Crops it to a square, makes it 512 x 512, and saves
  sangkap/static/art/pattern.webp (small: it repeats behind every page).
"""
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).parent.parent
SOURCE_DIR = ROOT / "docs" / "art_src"
OUT = ROOT / "sangkap" / "static" / "art" / "pattern.webp"
SIZE = 512
TOLERANCE = 38  # how far from the corner colour still counts as "background"


def find_source():
    for name in ("background.png", "background.webp", "background.jpg", "background.jpeg"):
        if (SOURCE_DIR / name).exists():
            return SOURCE_DIR / name
    sys.exit(f"Put your picture at {SOURCE_DIR / 'background.png'} first.")


def has_transparency(image):
    return image.mode == "RGBA" and image.getextrema()[3][0] < 250


def close(a, b):
    return all(abs(x - y) <= TOLERANCE for x, y in zip(a[:3], b[:3]))


def remove_plain_background(image):
    """Flood-fill from the four corners: background-coloured pixels become see-through."""
    image = image.convert("RGBA")
    width, height = image.size
    pixels = image.load()
    mask = Image.new("L", image.size, 255)
    alpha = mask.load()
    queue = deque()
    for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        queue.append((x, y, pixels[x, y]))
    while queue:
        x, y, colour = queue.popleft()
        if not (0 <= x < width and 0 <= y < height) or alpha[x, y] == 0:
            continue
        if not close(pixels[x, y], colour):
            continue
        alpha[x, y] = 0
        queue.extend(((x + 1, y, colour), (x - 1, y, colour), (x, y + 1, colour), (x, y - 1, colour)))
    # Soften the edge by one pixel, so there is no hard white rim.
    image.putalpha(mask.filter(ImageFilter.GaussianBlur(1)))
    return image


def main():
    source = find_source()
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    if not has_transparency(image):
        print("No see-through background found: removing the plain background...")
        image = remove_plain_background(image)
    side = min(image.size)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize((SIZE, SIZE), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, "WEBP", quality=82, method=6)
    print(f"Saved {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB). Restart the app to see it.")


if __name__ == "__main__":
    main()
