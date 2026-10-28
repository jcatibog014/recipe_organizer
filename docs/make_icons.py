"""Make the PNG app icons from sangkap/static/icons/logo.svg.

Phones and old browsers want PNG pictures in fixed sizes. Run this again
after changing the logo. Like take_screenshots.py, it uses Playwright + Edge:

    .venv\\Scripts\\python -m pip install playwright
    .venv\\Scripts\\python docs\\make_icons.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ICONS = Path(__file__).parent.parent / "sangkap" / "static" / "icons"
CREAM = "#fff8ee"  # the app's --bg colour

# (file, size, background, padding). The home-screen icons get a cream tile
# with 14% padding, so Android can crop them into a circle ("maskable").
SIZES = [
    ("icon-32.png", 32, None, 0),
    ("apple-touch-icon.png", 180, CREAM, 0.14),
    ("icon-192.png", 192, CREAM, 0.14),
    ("icon-512.png", 512, CREAM, 0.14),
]


def main():
    svg = (ICONS / "logo.svg").read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        for name, size, background, padding in SIZES:
            page = browser.new_page(viewport={"width": size, "height": size})
            inner = round(size * (1 - 2 * padding))
            page.set_content(f"""
                <style>
                  html, body {{ margin: 0; background: {background or 'transparent'}; }}
                  div {{ width: {size}px; height: {size}px; display: grid; place-items: center; }}
                  svg {{ width: {inner}px; height: {inner}px; }}
                </style>
                <div>{svg}</div>""")
            page.screenshot(path=ICONS / name, omit_background=background is None)
            page.close()
            print("saved", name)
        browser.close()


if __name__ == "__main__":
    main()
