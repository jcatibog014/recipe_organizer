import io

from PIL import Image
from sqlalchemy import select

from sangkap import db
from sangkap.models import Recipe

from conftest import add_recipe, log_in_as, post


def form(**overrides):
    data = {
        "action": "save", "title": "Chicken Adobo", "servings": "4", "prep_minutes": "10", "cook_minutes": "45",
        "tags": "Ulam, quick, ulam", "description": "", "notes": "Lola's way", "source_url": "",
        "row_kind": ["item", "section", "item", "item"],
        "row_section": ["", "For the sauce", "", ""],
        "row_amount": ["1", "", "1/2", ""],
        "row_unit": ["kg", "", "cup", ""],
        "row_name": ["Chicken", "", "toyo", ""],
        "row_note": ["thighs", "", "", ""],
        "row_optional": ["", "", "", ""],
        "step_text": ["Mix.", "", "Simmer."],
    }
    data.update(overrides)
    return data


def photo_bytes(size=(1600, 1200), fmt="JPEG"):
    out = io.BytesIO()
    Image.new("RGB", size, (255, 143, 177)).save(out, fmt)
    return out.getvalue()


def get_recipe(app, recipe_id):
    with app.app_context():
        recipe = db.session().get(Recipe, recipe_id)
        return {
            "title": recipe.title, "tags": [t.name for t in recipe.tags],
            "lines": [(l.amount, l.unit, l.ingredient.name, l.note, l.section) for l in recipe.ingredients],
            "steps": [s.text for s in recipe.steps], "notes": recipe.notes,
            "photo": recipe.photo and (recipe.photo.mime, recipe.photo.width),
        }


def test_add_a_recipe(app, owner_client):
    response = post(owner_client, "/recipes/new", form())
    assert response.status_code == 302
    recipe_id = int(response.headers["Location"].rsplit("/", 1)[1])
    assert get_recipe(app, recipe_id) == {
        "title": "Chicken Adobo", "tags": ["quick", "ulam"],
        # "toyo" is an alias: the line points at the catalog's "soy sauce".
        "lines": [(1.0, "kg", "chicken", "thighs", ""), (0.5, "cup", "soy sauce", "", "For the sauce")],
        "steps": ["Mix.", "Simmer."], "notes": "Lola's way", "photo": None,
    }
    page = owner_client.get(f"/recipes/{recipe_id}").data.decode()
    assert "Chicken Adobo" in page and "½ cup" in page and "For the sauce" in page


def test_form_errors_keep_what_was_typed(owner_client):
    response = post(owner_client, "/recipes/new", form(title="", row_amount=["lots", "", "1/2", ""]))
    assert response.status_code == 400
    page = response.data.decode()
    assert "Give your recipe a name." in page
    assert "Write an amount like" in page
    assert 'value="lots"' in page and 'value="toyo"' in page


def test_paste_turns_text_into_rows_without_saving(app, owner_client, owner_id):
    response = post(owner_client, "/recipes/new", form(action="paste", paste="2 cups rice\nsalt to taste"))
    assert response.status_code == 200
    page = response.data.decode()
    assert "Added 2 rows" in page and 'value="rice"' in page and 'value="to taste"' in page
    with app.app_context():
        assert db.session().scalar(select(Recipe)) is None


def test_more_rows_without_javascript(owner_client):
    page = post(owner_client, "/recipes/new", form(action="more")).data.decode()
    # 3 ingredient rows (the 4th is a heading) + 3 new ones + the JavaScript template.
    assert page.count('placeholder="Ingredient') == 3 + 3 + 1


def test_edit_replaces_lines_and_tags(app, owner_client, owner_id):
    recipe_id = add_recipe(app, owner_id, "Old", ["1 cup rice"], tags=["old"])
    page = owner_client.get(f"/recipes/{recipe_id}/edit").data.decode()
    assert 'value="rice"' in page and 'value="old"' in page
    post(owner_client, f"/recipes/{recipe_id}/edit", form(title="New", tags="fresh"))
    recipe = get_recipe(app, recipe_id)
    assert recipe["title"] == "New" and recipe["tags"] == ["fresh"] and len(recipe["lines"]) == 2


def test_scaling_servings(app, owner_client, owner_id):
    recipe_id = add_recipe(app, owner_id, "Rice", ["1 cup rice", "1/3 tsp salt"])
    page = owner_client.get(f"/recipes/{recipe_id}?servings=6").data.decode()
    assert "1 ½ cups" in page and "½ tsp" in page and "6 servings" in page


def test_other_users_recipes_are_not_found(app, owner_client, other_id):
    theirs = add_recipe(app, other_id, "Pedro's secret")
    for url in [f"/recipes/{theirs}", f"/recipes/{theirs}/edit", f"/recipes/{theirs}/cook",
                f"/recipes/{theirs}/photo"]:
        assert owner_client.get(url).status_code == 404
    for url in [f"/recipes/{theirs}/delete", f"/recipes/{theirs}/share", f"/recipes/{theirs}/favorite",
                f"/recipes/{theirs}/edit"]:
        assert post(owner_client, url, form()).status_code == 404
    assert "Pedro" not in owner_client.get("/").data.decode()


def test_delete_and_favorite(app, owner_client, owner_id):
    recipe_id = add_recipe(app, owner_id, "Gone soon")
    post(owner_client, f"/recipes/{recipe_id}/favorite")
    assert "(favorite)" in owner_client.get("/?favorites=1").data.decode()
    post(owner_client, f"/recipes/{recipe_id}/delete")
    assert owner_client.get(f"/recipes/{recipe_id}").status_code == 404


def test_list_filters_and_sorts(app, owner_client, owner_id):
    add_recipe(app, owner_id, "Banana cue", tags=["merienda"], prep_minutes=5, cook_minutes=10)
    add_recipe(app, owner_id, "Adobo", tags=["ulam"], prep_minutes=10, cook_minutes=45)
    page = owner_client.get("/?tag=merienda").data.decode()
    assert "Banana cue" in page and "Adobo" not in page
    page = owner_client.get("/?sort=az").data.decode()
    assert page.index("Adobo") < page.index("Banana cue")
    page = owner_client.get("/?sort=quick").data.decode()
    assert page.index("Banana cue") < page.index("Adobo")


def test_photo_upload_is_resized_and_served(app, owner_client):
    data = form()
    data["photo"] = (io.BytesIO(photo_bytes()), "dish.jpg")
    response = post(owner_client, "/recipes/new", data, content_type="multipart/form-data")
    recipe_id = int(response.headers["Location"].rsplit("/", 1)[1])
    assert get_recipe(app, recipe_id)["photo"] == ("image/webp", 1000)
    photo = owner_client.get(f"/recipes/{recipe_id}/photo")
    assert photo.mimetype == "image/webp" and "immutable" in photo.headers["Cache-Control"]
    post(owner_client, f"/recipes/{recipe_id}/photo/delete")
    assert get_recipe(app, recipe_id)["photo"] is None


def test_a_bad_photo_still_saves_the_recipe(app, owner_client):
    data = form()
    data["photo"] = (io.BytesIO(b"not a picture"), "virus.jpg")
    response = post(owner_client, "/recipes/new", data, content_type="multipart/form-data")
    assert "/edit" in response.headers["Location"]
    assert "a photo we can read" in owner_client.get(response.headers["Location"]).data.decode()


def test_cook_mode(app, owner_client, owner_id):
    recipe_id = add_recipe(app, owner_id, "Rice", ["1 cup rice"], steps=["Wash.", "Boil."])
    page = owner_client.get(f"/recipes/{recipe_id}/cook?servings=8").data.decode()
    assert "Wash." in page and "Boil." in page and "2 cups" in page and "data-cook" in page


def test_demo_recipe_limit(app, client):
    post(client, "/demo")
    from sangkap.views import recipes
    original = recipes.DEMO_MAX_RECIPES
    recipes.DEMO_MAX_RECIPES = 9  # the demo already has 9
    try:
        assert post(client, "/recipes/new", form()).status_code == 403
    finally:
        recipes.DEMO_MAX_RECIPES = original


def test_logged_in_user_can_open_another_user_session_safely(app, client, owner_id, other_id):
    log_in_as(client, other_id)
    assert client.get("/").status_code == 200


def test_search_my_recipes_by_name(app, owner_client, owner_id):
    add_recipe(app, owner_id, "Chicken Adobo", tags=["ulam"], description="Salty and sour")
    add_recipe(app, owner_id, "Leche Flan", tags=["dessert"], is_favorite=True)
    add_recipe(app, owner_id, "Pedro's 100% Pancit")
    page = owner_client.get("/?q=adobo").data.decode()
    assert "1 recipe match “adobo”" in page and "Chicken Adobo" in page and "Leche Flan" not in page
    assert "Chicken Adobo" in owner_client.get("/?q=sour").data.decode()          # the description too
    page = owner_client.get("/?q=100%25").data.decode()                            # % is a plain character
    assert "Pancit" in page and "Adobo" not in page
    page = owner_client.get("/?q=flan&favorites=1&tag=dessert").data.decode()
    assert "Leche Flan" in page
    page = owner_client.get("/?q=halo-halo").data.decode()
    assert "No Recipes Match" in page and "/discover?q=halo-halo" in page
