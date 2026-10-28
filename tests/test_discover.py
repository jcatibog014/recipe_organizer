from sqlalchemy import func, select

from sangkap import mealdb
from sangkap.models import Recipe

from conftest import add_recipe, post


def test_discover_starts_with_filipino_recipes(owner_client):
    page = owner_client.get("/discover").data.decode()
    assert "Filipino favorites" in page and "Bistek" in page and "Tortang Talong" in page
    assert "TheMealDB" in page  # the credit


def test_discover_by_ingredient_uses_aliases(owner_client, offline_mealdb):
    page = owner_client.get("/discover?have=bawang").data.decode()
    assert "Eggplant Adobo" in page
    assert any("filter.php?i=garlic" in url for url in offline_mealdb)


def test_discover_by_name(owner_client):
    assert "Eggplant Adobo" in owner_client.get("/discover?q=adobo").data.decode()


def test_discover_shows_your_own_matches_too(app, owner_client, owner_id):
    add_recipe(app, owner_id, "My Adobo", ["1 kg chicken"])
    page = owner_client.get("/discover?q=adobo").data.decode()
    assert "Already in your recipes" in page and "My Adobo" in page


def test_follow_a_recipe_right_away(owner_client):
    page = owner_client.get("/discover/53069?servings=8").data.decode()
    assert "Bistek" in page and "Save to my recipes" in page
    assert "10 tbsp" in page  # 5 tablespoons for 4, shown for 8
    assert "Marinate beef" in owner_client.get("/discover/53069/cook").data.decode()


def test_unknown_meal_is_not_found(owner_client):
    assert owner_client.get("/discover/99999").status_code == 404
    assert owner_client.get("/discover/abc").status_code == 404


def test_save_copies_it_into_my_recipes_once(app, owner_client, owner_id, ctx):
    response = post(owner_client, "/discover/53069/save")
    recipe_id = int(response.headers["Location"].rsplit("/", 1)[1])
    recipe = ctx.get(Recipe, recipe_id)
    assert (recipe.title, recipe.source, recipe.external_id, recipe.user_id) == (
        "Bistek", "themealdb", "53069", owner_id)
    assert [line.ingredient.name for line in recipe.ingredients][:2] == ["beef", "soy sauce"]
    assert sorted(tag.name for tag in recipe.tags) == ["beef", "filipino"]
    assert "Video: https://www.youtube.com" in recipe.notes
    assert recipe.photo is None  # the test can't download pictures, and that's fine

    again = post(owner_client, "/discover/53069/save")
    assert again.headers["Location"] == f"/recipes/{recipe_id}"
    assert ctx.scalar(select(func.count()).select_from(Recipe)) == 1
    page = owner_client.get(f"/recipes/{recipe_id}").data.decode()
    assert "Recipe data and imagery" in page
    assert "Open your saved copy" in owner_client.get("/discover/53069").data.decode()


def test_saved_recipes_are_searchable_by_our_names(app, owner_client, owner_id):
    post(owner_client, "/discover/53069/save")
    # TheMealDB says "Beef" and "Soy Sauce"; our search finds it by "baka" and "toyo".
    page = owner_client.get("/search?have=baka,toyo").data.decode()
    assert "Bistek" in page and "1 recipe found" in page


def test_demo_save_limit(app, client, monkeypatch):
    from sangkap.views import discover
    monkeypatch.setattr(discover, "DEMO_MAX_SAVED", 0)
    post(client, "/demo")
    assert post(client, "/discover/53069/save").status_code == 403


def test_when_themealdb_is_down(owner_client, monkeypatch):
    def broken(url):
        raise OSError("no internet")
    monkeypatch.setattr(mealdb, "FETCH_JSON", broken)
    page = owner_client.get("/discover").data.decode()
    assert "Discover is unavailable" in page
    assert owner_client.get("/discover/53069").status_code == 503
    assert owner_client.get("/").status_code == 200  # the rest of the app is fine
