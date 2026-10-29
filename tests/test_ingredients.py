from sqlalchemy import select

from sangkap import ingredients
from sangkap.ingredients import CATALOG, normalize, resolve
from sangkap.models import Ingredient, IngredientAlias

from conftest import add_recipe


def test_normalize():
    assert normalize("  Garlic  CLOVES. ") == "garlic cloves"
    assert normalize("- Kamatis") == "kamatis"
    assert normalize("") == ""


def test_catalog_names_and_aliases_never_clash():
    seen = set()
    for name, kind, aliases in CATALOG:
        assert kind in ingredients.KINDS
        assert name == normalize(name)
        for word in [name, *aliases]:
            assert word not in seen, f"{word!r} is listed twice"
            seen.add(word)


def test_add_catalog_is_safe_to_run_again(ctx):
    # The app fixture added it once already.
    assert ingredients.add_catalog(ctx) == 0
    assert ctx.scalar(select(Ingredient).where(Ingredient.name == "garlic")).is_seeded


def test_resolve_by_name_alias_and_plural(ctx):
    garlic = resolve(ctx, "Garlic")
    assert garlic.name == "garlic"
    assert resolve(ctx, "bawang") is garlic          # Filipino alias
    assert resolve(ctx, "kamatis").name == "tomato"
    assert resolve(ctx, "aubergine").name == "eggplant"
    assert resolve(ctx, "okras").name == "okra"      # simple plural
    assert resolve(ctx, "dragon fruit") is None


def test_get_or_create_adds_once(ctx):
    first = ingredients.get_or_create(ctx, "Dragon  Fruit")
    second = ingredients.get_or_create(ctx, "dragon fruit")
    assert first is second and first.name == "dragon fruit" and not first.is_seeded


def test_suggestions_hide_other_users_new_ingredients(app, owner_id, other_id, ctx):
    add_recipe(app, other_id, "Secret", ["1 cup lola's secret sauce"])
    add_recipe(app, owner_id, "Mine", ["2 pcs kalamansi tarts"])
    names = ingredients.suggestions(ctx, owner_id)
    assert "garlic" in names
    assert "kalamansi tarts" in names
    assert "lola's secret sauce" not in names


def test_usage_counts_each_recipe_once(app, owner_id, ctx):
    add_recipe(app, owner_id, "Adobo", ["1 head garlic", "3 cloves garlic, for the sauce", "1 kg chicken"])
    add_recipe(app, owner_id, "Sinangag", ["8 cloves garlic", "4 cups rice"])
    counts = {ingredient.name: count for ingredient, count in ingredients.usage(ctx, owner_id)}
    assert counts == {"garlic": 2, "chicken": 1, "rice": 1}


def test_merge_moves_only_my_lines_and_keeps_an_alias(app, owner_id, other_id, ctx):
    mine = add_recipe(app, owner_id, "Soup", ["2 pcs sibuyas bombay"])
    add_recipe(app, other_id, "Theirs", ["1 pc sibuyas bombay"])
    source = resolve(ctx, "sibuyas bombay")

    target, moved = ingredients.merge(ctx, owner_id, source, "onion")
    ctx.commit()
    assert (target.name, moved) == ("onion", 1)
    # Pedro still uses it, so it stays (and no alias yet).
    assert resolve(ctx, "sibuyas bombay") is source
    assert ctx.get(type(source), source.id) is not None

    other_source = resolve(ctx, "sibuyas bombay")
    ingredients.merge(ctx, other_id, other_source, "onion")
    ctx.commit()
    # Now nobody uses it: deleted, and its name is an alias of onion.
    assert resolve(ctx, "sibuyas bombay").name == "onion"
    assert ctx.scalar(select(IngredientAlias).where(IngredientAlias.alias == "sibuyas bombay"))
    assert mine


def test_merge_into_itself_does_nothing(ctx, app, owner_id):
    add_recipe(app, owner_id, "Rice", ["1 cup rice"])
    rice = resolve(ctx, "rice")
    assert ingredients.merge(ctx, owner_id, rice, "kanin") == (rice, 0)


def test_delete_unused_keeps_starters_and_used(app, owner_id, ctx):
    add_recipe(app, owner_id, "Used", ["1 pc star fruit"])
    ingredients.get_or_create(ctx, "unused thing")
    ctx.commit()
    assert ingredients.delete_unused(ctx) == 1
    assert resolve(ctx, "star fruit") and resolve(ctx, "garlic") and resolve(ctx, "unused thing") is None
