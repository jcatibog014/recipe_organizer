"""Take the README screenshots (docs/screenshots/*.png).

It logs in with "Try Demo", so only sample recipes show. It uses
Microsoft Edge, which Windows already has, through Playwright. Playwright
is only a tool for this script, so it is not in requirements.txt:

    .venv\\Scripts\\python -m pip install playwright
    .venv\\Scripts\\flask --app sangkap run --port 5003      (in another terminal)
    .venv\\Scripts\\python docs\\take_screenshots.py

Add a line to PAGES when a page is added. Discover needs the internet (TheMealDB).
"""
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5003"
OUT = Path(__file__).parent / "screenshots"
DESKTOP = {"width": 1200, "height": 800}
PHONE = {"width": 390, "height": 844}

# (file name, address, theme, screen size). "{adobo}" is the demo's Chicken Adobo;
# "{picked}" ticks chicken, garlic, ginger and rice on "What can I cook?".
PAGES = [
    ("recipes.png", "/", "light", DESKTOP),
    ("recipes-dark.png", "/", "dark", DESKTOP),
    ("recipe.png", "/recipes/{adobo}?servings=6", "light", DESKTOP),
    ("edit-recipe.png", "/recipes/{adobo}/edit", "light", DESKTOP),
    ("what-can-i-cook.png", "/ingredients?{picked}&match=missing1", "light", DESKTOP),
    ("what-can-i-cook-dark.png", "/ingredients?{picked}&match=missing1", "dark", DESKTOP),
    ("ingredients.png", "/ingredients/manage", "light", DESKTOP),
    ("discover.png", "/discover", "light", DESKTOP),
    ("meal-plan.png", "/plan", "light", DESKTOP),
    ("shopping-list.png", "/plan/shopping", "dark", DESKTOP),
    ("cook-mode.png", "/recipes/{adobo}/cook", "dark", PHONE),
    ("phone.png", "/", "light", PHONE),
    ("settings.png", "/settings", "light", DESKTOP),
    ("styleguide.png", "/styleguide", "light", DESKTOP),
]


def demo_page(browser, theme, size):
    page = browser.new_page(viewport=size, color_scheme=theme)
    page.goto(f"{BASE}/login")
    page.get_by_role("button", name="Try Demo").click()
    page.wait_for_load_state("networkidle")
    return page


def find_adobo(page):
    page.goto(f"{BASE}/?q=Chicken+Adobo")
    match = re.search(r'/recipes/(\d+)"', page.content())
    return match.group(1)


def picked_ingredients(page, names=("Chicken", "Garlic", "Ginger", "Rice")):
    """The ?have=... part that ticks these ingredients (their ids differ per database)."""
    page.goto(f"{BASE}/ingredients")
    html = page.content()
    ids = [re.search(rf'value="(\d+)"[^>]*>\s*<span>{name}</span>', html).group(1) for name in names]
    return "&".join(f"have={i}" for i in ids)


def shoot(page, name, path, size):
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")  # fonts and pictures are in
    page.wait_for_timeout(500)
    # Sticky bars (Save, Find recipes) would float mid-picture in a full-page shot,
    # so pin them where they are in the page first.
    # The sidebar is as tall as the screen and stays put while you scroll; in a
    # full-page picture, stretch it down the whole page instead.
    page.add_style_tag(content=".find-bar, .sticky-actions { position: static !important; }"
                       " .has-sidebar .sidebar { position: static !important; height: auto !important; }")
    page.screenshot(path=OUT / name, full_page=size is DESKTOP)
    print("saved", name)


def shoot_shared(browser, page, adobo):
    """Turn sharing on, open the link as a stranger, then turn it off again."""
    page.goto(f"{BASE}/recipes/{adobo}")
    page.get_by_role("button", name="Create a share link").click()
    link = page.get_by_label("Share link").input_value()
    stranger = browser.new_page(viewport=DESKTOP, color_scheme="light")
    stranger.goto(link)
    stranger.wait_for_load_state("networkidle")
    stranger.screenshot(path=OUT / "shared-recipe.png", full_page=True)
    stranger.close()
    page.get_by_role("button", name="Stop sharing").click()
    print("saved shared-recipe.png")


def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")

        page = browser.new_page(viewport=DESKTOP, color_scheme="light")
        page.goto(f"{BASE}/login")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=OUT / "login.png")
        page.close()
        print("saved login.png")

        pages = {}
        for name, path, theme, size in PAGES:
            key = (theme, size["width"])
            if key not in pages:
                pages[key] = demo_page(browser, theme, size)
            page = pages[key]
            if "{adobo}" in path:
                path = path.replace("{adobo}", find_adobo(page))
            if "{picked}" in path:
                path = path.replace("{picked}", picked_ingredients(page))
            shoot(page, name, path, size)
        light = pages[("light", DESKTOP["width"])]
        shoot_shared(browser, light, find_adobo(light))
        browser.close()


if __name__ == "__main__":
    main()
