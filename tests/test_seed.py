"""The demo's sample recipes are clean data."""
from sangkap import paste
from sangkap.display import recipe_emoji
from sangkap.ingredients import resolve
from sangkap.seed import DEMO_PLAN, DEMO_RECIPES


def test_every_sample_line_reads_cleanly():
    for sample in DEMO_RECIPES:
        rows = paste.parse_block(sample["ingredients"])
        assert rows, sample["title"]
        for row in rows:
            if row["kind"] == "item":
                assert row["name"], (sample["title"], row)


def test_every_sample_ingredient_is_in_the_catalog(ctx):
    """So search by "bawang" or "manok" finds the demo recipes, and no odd names are added."""
    unknown = set()
    for sample in DEMO_RECIPES:
        for row in paste.parse_block(sample["ingredients"]):
            if row["kind"] == "item" and resolve(ctx, row["name"]) is None:
                unknown.add(row["name"])
    # Only a few dish-specific extras are allowed to be new.
    assert unknown <= {"lemon-lime soda", "leche flan"}, unknown


def test_plan_uses_sample_titles():
    titles = {sample["title"] for sample in DEMO_RECIPES}
    assert {title for _day, _meal, title in DEMO_PLAN} <= titles
    assert len(titles) == len(DEMO_RECIPES) == 20


def test_sample_pictures_vary():
    emojis = {recipe_emoji({"tags": [t.strip() for t in s["tags"].split(",")]}) for s in DEMO_RECIPES}
    assert len(emojis) >= 8
