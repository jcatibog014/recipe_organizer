from sqlalchemy import func, select

from sangkap.ingredients import resolve
from sangkap.models import Recipe, Tag

from conftest import add_recipe, post


def test_tags_page_counts_recipes(app, owner_client, owner_id):
    add_recipe(app, owner_id, "A", tags=["soup", "quick"])
    add_recipe(app, owner_id, "B", tags=["soup"])
    page = owner_client.get("/tags").data.decode()
    assert "#soup" in page and 'aria-label="2 recipes"' in page and 'aria-label="1 recipe"' in page


def test_rename_a_tag(app, owner_client, owner_id, ctx):
    add_recipe(app, owner_id, "A", tags=["sopas"])
    tag = ctx.scalar(select(Tag).where(Tag.name == "sopas"))
    post(owner_client, f"/tags/{tag.id}/rename", {"name": "Soup"})
    ctx.expire_all()
    assert ctx.get(Tag, tag.id).name == "soup"


def test_renaming_to_an_existing_tag_merges(app, owner_client, owner_id, ctx):
    a = add_recipe(app, owner_id, "A", tags=["sopas"])
    b = add_recipe(app, owner_id, "B", tags=["sopas", "soup"])
    sopas = ctx.scalar(select(Tag).where(Tag.name == "sopas"))
    post(owner_client, f"/tags/{sopas.id}/rename", {"name": "soup"})
    ctx.expire_all()
    assert ctx.scalar(select(func.count()).select_from(Tag)) == 1
    assert [t.name for t in ctx.get(Recipe, a).tags] == ["soup"]
    assert [t.name for t in ctx.get(Recipe, b).tags] == ["soup"]  # not twice


def test_delete_a_tag_keeps_recipes(app, owner_client, owner_id, ctx):
    recipe_id = add_recipe(app, owner_id, "A", tags=["old"])
    tag = ctx.scalar(select(Tag).where(Tag.name == "old"))
    post(owner_client, f"/tags/{tag.id}/delete")
    ctx.expire_all()
    assert ctx.get(Recipe, recipe_id).tags == []


def test_other_users_tags_are_not_found(app, owner_client, other_id, ctx):
    add_recipe(app, other_id, "X", tags=["theirs"])
    tag = ctx.scalar(select(Tag).where(Tag.name == "theirs"))
    assert post(owner_client, f"/tags/{tag.id}/rename", {"name": "mine"}).status_code == 404
    assert post(owner_client, f"/tags/{tag.id}/delete").status_code == 404


def test_ingredients_page(app, owner_client, owner_id):
    add_recipe(app, owner_id, "Adobo", ["1 kg chicken", "1 head garlic"])
    add_recipe(app, owner_id, "Sinangag", ["8 cloves garlic"])
    page = owner_client.get("/ingredients").data.decode()
    assert "Meat" in page and "Chicken" in page and 'aria-label="2 recipes"' in page


def test_ingredient_page_and_merge(app, owner_client, owner_id, ctx):
    add_recipe(app, owner_id, "Salad", ["2 pcs tomatoe"])  # a typo
    typo = resolve(ctx, "tomatoe")
    assert typo.name == "tomatoe" and not typo.is_seeded
    assert "Salad" in owner_client.get(f"/ingredients/{typo.id}").data.decode()

    response = post(owner_client, f"/ingredients/{typo.id}/merge", {"target": "tomato"})
    tomato = resolve(ctx, "tomato")
    assert response.headers["Location"] == f"/ingredients/{tomato.id}"
    assert "Salad" in owner_client.get(f"/ingredients/{tomato.id}").data.decode()
    # The typo is gone, and typing it again finds tomato.
    ctx.expire_all()
    assert resolve(ctx, "tomatoe").id == tomato.id


def test_other_users_new_ingredients_are_hidden(app, owner_client, other_id, ctx):
    add_recipe(app, other_id, "Secret", ["1 cup lola's secret sauce"])
    secret = resolve(ctx, "lola's secret sauce")
    assert owner_client.get(f"/ingredients/{secret.id}").status_code == 404
    assert post(owner_client, f"/ingredients/{secret.id}/merge", {"target": "x"}).status_code == 404
    # A starter ingredient is fine to open, even with no recipes.
    assert owner_client.get(f"/ingredients/{resolve(ctx, 'garlic').id}").status_code == 200
