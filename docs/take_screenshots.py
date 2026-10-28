"""Take the README screenshots (docs/screenshots/*.png).

It logs in with "Try the demo", so only sample recipes show. It uses
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

# (file name, address, theme, screen size). "{adobo}" is the demo's Chicken Adobo.
PAGES = [
    ("recipes.png", "/", "light", DESKTOP),
    ("recipes-dark.png", "/", "dark", DESKTOP),
    ("recipe.png", "/recipes/{adobo}?servings=6", "light", DESKTOP),
    ("edit-recipe.png", "/recipes/{adobo}/edit", "light", DESKTOP),
    ("search.png", "/search?have=chicken%2C+garlic%2C+ginger%2C+rice&mode=pantry&missing=1", "light", DESKTOP),
    ("ingredients.png", "/ingredients", "light", DESKTOP),
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
    page.get_by_role("button", name="Try the demo").click()
    page.wait_for_load_state("networkidle")
    return page


def find_adobo(page):
    page.goto(f"{BASE}/search?q=Chicken+Adobo")
    match = re.search(r'/recipes/(\d+)"', page.content())
    return match.group(1)


def shoot(page, name, path, size):
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")  # fonts and pictures are in
    page.wait_for_timeout(500)
    # The edit form has a sticky Save bar, so show it as one screen, the way people see it.
    page.screenshot(path=OUT / name, full_page=size is DESKTOP and "edit" not in name)
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
            shoot(page, name, path, size)
        light = pages[("light", DESKTOP["width"])]
        shoot_shared(browser, light, find_adobo(light))
        browser.close()


if __name__ == "__main__":
    main()
