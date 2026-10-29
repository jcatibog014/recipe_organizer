from datetime import date, timedelta

import pytest

from sangkap import shopping
from sangkap.dates import today, week_start
from sangkap.ingredients import resolve
from sangkap.models import PlanEntry, Recipe

from conftest import add_recipe, post


# ---------- Adding up (no database) ----------

def item(**amounts):
    entry = shopping.Item(name="x", kind="other")
    for unit, amount in amounts.items():
        entry.add(amount, unit)
    return entry


@pytest.mark.parametrize("amounts, expected", [
    ({"tbsp": 3}, ["3 tbsp"]),
    ({"cup": 1, "tbsp": 2}, ["1 ⅛ cups"]),
    ({"g": 500, "kg": 1}, ["1 ½ kg"]),
    ({"pc": 2, "cup": 1}, ["1 cup", "2 pcs"]),
    ({"tsp": 1.5}, ["1 ½ tsp"]),
    ({"": 3}, ["3"]),
    ({"cup": 2, "tbsp": 3}, ["2 ¼ cups"]),  # 2.1875 rounds up, never "2.19"
    ({"cup": 1 / 3}, ["⅓ cup"]),            # thirds stay thirds
    ({"pc": 0.3}, ["⅜ pc"]),
])
def test_totals(amounts, expected):
    assert item(**amounts).quantities() == expected


# ---------- The shopping list from a plan ----------

@pytest.fixture
def week(app, owner_id, ctx):
    adobo = add_recipe(app, owner_id, "Adobo", ["1 kg chicken", "1/2 cup soy sauce", "1 head garlic",
                                                "salt to taste", "1 cup water"], servings=4)
    sinangag = add_recipe(app, owner_id, "Sinangag", ["4 cups rice", "8 cloves garlic", "2 tbsp soy sauce",
                                                      ("1 pc egg", {"is_optional": True})], servings=4)
    monday = week_start(today())
    ctx.add_all([
        PlanEntry(user_id=owner_id, recipe_id=adobo, day=monday, meal="dinner", servings=8),  # double
        PlanEntry(user_id=owner_id, recipe_id=sinangag, day=monday + timedelta(days=1), meal="breakfast",
                  servings=4),
        # Next week's meal isn't on this week's list.
        PlanEntry(user_id=owner_id, recipe_id=adobo, day=monday + timedelta(days=7), meal="lunch", servings=4),
    ])
    ctx.commit()
    return monday


def test_shopping_list_scales_and_adds_up(app, week, owner_id, ctx):
    from sqlalchemy import select
    entries = ctx.scalars(select(PlanEntry).where(PlanEntry.day < week + timedelta(days=7))).all()
    groups = dict(shopping.build(entries))
    by_name = {i.name: i for items in groups.values() for i in items}
    assert by_name["chicken"].quantities() == ["2 kg"]               # 1 kg for 4, planned for 8
    assert by_name["soy sauce"].quantities() == ["1 ⅛ cups"]         # 1 cup (doubled) + 2 tbsp
    assert by_name["garlic"].quantities() == ["8 cloves", "2 heads"]  # can't be added
    assert by_name["salt"].loose and by_name["salt"].quantities() == []
    assert "egg" not in by_name                                       # optional: left out
    assert "water" not in by_name                                     # from the tap
    assert by_name["garlic"].recipes == ["Adobo", "Sinangag"]
    assert list(groups) == ["produce", "meat", "pantry", "spice"]     # shelf order


def test_plan_page_and_shopping_page(week, owner_client):
    page = owner_client.get("/plan").data.decode()
    assert "Adobo" in page and "Sinangag" in page and "Serves 8" in page
    shop = owner_client.get("/plan/shopping").data.decode()
    assert "2 kg" in shop and "1 ⅛ cups" in shop and ">to taste<" in shop
    nothing = owner_client.get(f"/plan/shopping?week={(week + timedelta(days=14)).isoformat()}").data.decode()
    assert "Nothing to Buy Yet" in nothing


def test_add_and_remove_a_meal(app, owner_client, owner_id, ctx):
    recipe_id = add_recipe(app, owner_id, "Tinola", servings=5)
    day = date(2026, 11, 4)  # a Wednesday
    response = post(owner_client, "/plan/add", {"day": day.isoformat(), "meal": "lunch", "recipe_id": recipe_id,
                                                "servings": "", "week": "2026-11-02"})
    assert response.headers["Location"].startswith("/plan?week=2026-11-02")
    page = owner_client.get("/plan?week=2026-11-04").data.decode()  # any day finds its week
    assert "Tinola" in page and "Serves 5" in page and "Nov 2–8, 2026" in page

    from sqlalchemy import select
    entry = ctx.scalar(select(PlanEntry))
    post(owner_client, f"/plan/{entry.id}/delete")
    assert "Tinola" not in owner_client.get("/plan?week=2026-11-02").data.decode().split("Add a meal")[0]


def test_plan_checks_its_input(app, owner_client, owner_id, other_id):
    mine = add_recipe(app, owner_id, "Mine")
    theirs = add_recipe(app, other_id, "Theirs")
    base = {"day": "2026-11-04", "meal": "lunch", "recipe_id": mine}
    assert post(owner_client, "/plan/add", {**base, "meal": "midnight"}).status_code == 400
    assert post(owner_client, "/plan/add", {**base, "day": "soon"}).status_code == 400
    assert post(owner_client, "/plan/add", {**base, "recipe_id": theirs}).status_code == 404
    assert post(owner_client, "/plan/add", {**base, "recipe_id": "x"}).status_code == 400


def test_other_users_plan_entries(app, owner_client, other_id, ctx):
    recipe_id = add_recipe(app, other_id, "Theirs")
    entry = PlanEntry(user_id=other_id, recipe_id=recipe_id, day=today(), meal="lunch", servings=2)
    ctx.add(entry)
    ctx.commit()
    assert "Theirs" not in owner_client.get("/plan").data.decode()
    assert post(owner_client, f"/plan/{entry.id}/delete").status_code == 404


def test_deleting_a_recipe_takes_it_off_the_plan(app, week, owner_client, ctx):
    from sqlalchemy import func, select
    adobo = ctx.scalar(select(Recipe).where(Recipe.title == "Adobo"))
    post(owner_client, f"/recipes/{adobo.id}/delete")
    assert ctx.scalar(select(func.count()).select_from(PlanEntry)) == 1
    assert resolve(ctx, "chicken") is not None


def test_plan_page_layout(week, owner_client):
    page = owner_client.get("/plan").data.decode()
    # Meal type as a coloured pill, removing inside the ⋯ menu, a dashed Add button per day.
    assert 'class="meal-pill meal-dinner">Dinner<' in page
    assert 'class="meal-menu"' in page and 'aria-label="Remove Adobo from Monday">Remove<' in page and "Open recipe" in page
    assert page.count('class="add-meal"') == 7
    # The week picker and Today, and today's column is marked.
    assert 'aria-label="Previous week"' in page and ">Today</a>" in page and 'aria-current="date"' in page
    assert '<span class="visually-hidden">(today)</span>' in page
