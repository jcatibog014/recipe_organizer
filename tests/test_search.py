"""Search by ingredient: every mode against a fixed little recipe box."""
import pytest
from sqlalchemy import event, select

from sangkap import db, search
from sangkap.ingredients import resolve
from sangkap.models import Tag

from conftest import add_recipe

BOX = {
    "Adobo": (["1 kg chicken", "1/2 cup soy sauce", "1/3 cup vinegar", "1 head garlic",
               "3 cloves garlic, for frying"], ["ulam"], {"prep_minutes": 10, "cook_minutes": 45}),
    "Tinola": (["1 kg chicken", "1 thumb ginger", "2 pcs chayote", ("1 cup malunggay", {"is_optional": True})],
               ["soup"], {"prep_minutes": 10, "cook_minutes": 30}),
    "Sinangag": (["4 cups rice", "8 cloves garlic", "1 tsp salt"], ["rice", "quick"],
                 {"prep_minutes": 5, "cook_minutes": 10, "is_favorite": True}),
    "Ginataang Hipon": (["500 g shrimp", "2 cups coconut milk", "4 cloves garlic"], ["ulam"],
                        {"notes": "Spicy version: add sili"}),
}


@pytest.fixture
def box(app, owner_id, other_id):
    ids = {title: add_recipe(app, owner_id, title, lines, tags=tags, **fields)
           for title, (lines, tags, fields) in BOX.items()}
    # Another user's chicken recipe must never show up.
    add_recipe(app, other_id, "Pedro's Chicken", ["1 kg chicken", "1 head garlic"])
    return ids


def ids_of(s, *names):
    return [resolve(s, name).id for name in names]


def titles(s, owner_id, **query):
    return [r.recipe.title for r in search.run(s, owner_id, search.Query(**query))]


def test_all_needs_every_ingredient(box, ctx, owner_id):
    assert titles(ctx, owner_id, have=ids_of(ctx, "chicken", "garlic")) == ["Adobo"]
    assert titles(ctx, owner_id, have=ids_of(ctx, "garlic")) == ["Adobo", "Ginataang Hipon", "Sinangag"]


def test_aliases_find_the_same_ingredient(box, ctx, owner_id):
    # "bawang" and "manok" are the Filipino names of garlic and chicken.
    assert titles(ctx, owner_id, have=ids_of(ctx, "bawang", "manok")) == ["Adobo"]


def test_garlic_twice_counts_once(box, ctx, owner_id):
    # Adobo has garlic on two lines; "all" still matches 2 of 2, not 3.
    results = search.run(ctx, owner_id, search.Query(have=ids_of(ctx, "chicken", "garlic")))
    assert results[0].matched == ["chicken", "garlic"]


def test_any_puts_the_best_matches_first(box, ctx, owner_id):
    assert titles(ctx, owner_id, mode="any", have=ids_of(ctx, "chicken", "garlic", "ginger")) == [
        "Adobo", "Tinola", "Ginataang Hipon", "Sinangag"]


def test_pantry_counts_missing_needed_ingredients(box, ctx, owner_id):
    have = ids_of(ctx, "chicken", "ginger", "garlic", "rice")
    # Tinola misses chayote only (malunggay is optional); Sinangag misses salt;
    # Adobo misses soy sauce and vinegar; Ginataang Hipon misses shrimp and coconut milk.
    assert titles(ctx, owner_id, mode="pantry", have=have, missing_max=0) == []
    assert titles(ctx, owner_id, mode="pantry", have=have, missing_max=1) == ["Sinangag", "Tinola"]
    results = search.run(ctx, owner_id, search.Query(mode="pantry", have=have, missing_max=2))
    # Fewest missing first; then the most matched (Adobo uses 2 of yours, the hipon 1).
    assert [(r.recipe.title, r.missing, r.optional) for r in results] == [
        ("Sinangag", ["salt"], []),
        ("Tinola", ["chayote"], ["malunggay"]),
        ("Adobo", ["soy sauce", "vinegar"], []),
        ("Ginataang Hipon", ["shrimp", "coconut milk"], []),
    ]


def test_staples_never_count_as_missing(box, ctx, owner_id):
    have = ids_of(ctx, "rice", "garlic")
    assert titles(ctx, owner_id, mode="pantry", have=have, missing_max=0) == []  # Sinangag needs salt
    staples = ids_of(ctx, *search.STAPLES)
    results = search.run(ctx, owner_id, search.Query(mode="pantry", have=have, missing_max=0, staples=staples))
    assert [(r.recipe.title, r.missing) for r in results] == [("Sinangag", [])]


def test_without(box, ctx, owner_id):
    assert titles(ctx, owner_id, without=ids_of(ctx, "chicken", "shrimp")) == ["Sinangag"]
    assert titles(ctx, owner_id, have=ids_of(ctx, "garlic"), without=ids_of(ctx, "rice")) == [
        "Adobo", "Ginataang Hipon"]


def test_words_tags_time_and_favorites(box, ctx, owner_id):
    assert titles(ctx, owner_id, text="SPICY") == ["Ginataang Hipon"]  # found in the notes
    assert titles(ctx, owner_id, text="100%") == []                    # % is a plain character
    ulam = ctx.scalar(select(Tag).where(Tag.user_id == owner_id, Tag.name == "ulam"))
    assert titles(ctx, owner_id, tag_ids=[ulam.id]) == ["Adobo", "Ginataang Hipon"]
    assert titles(ctx, owner_id, max_minutes=45) == ["Sinangag", "Tinola"]  # no times = not counted
    assert titles(ctx, owner_id, favorites=True) == ["Sinangag"]


def test_like_pattern_escapes():
    assert search.like_pattern("50%_off\\") == "%50\\%\\_off\\\\%"


def test_results_load_in_a_fixed_number_of_queries(app, box, owner_id):
    """No N+1: 4 results or 40, the search takes the same few queries."""
    with app.app_context():
        s = db.session()
        have = ids_of(s, "garlic")
        statements = []
        listener = lambda *args: statements.append(args[2])  # noqa: E731
        event.listen(db.engine(), "before_cursor_execute", listener)
        try:
            results = search.run(s, owner_id, search.Query(mode="any", have=have))
            for result in results:  # touching everything the page shows
                _ = [line.ingredient.name for line in result.recipe.ingredients]
                _ = [tag.name for tag in result.recipe.tags], result.recipe.photo
        finally:
            event.remove(db.engine(), "before_cursor_execute", listener)
    assert len(results) == 3
    # 1 search + lines + their ingredients + tags + photos
    assert len(statements) <= 5, statements


# ---------- The "What can I cook?" page (/ingredients) ----------

def picker_url(ctx, *names, match=None):
    url = "/ingredients?" + "&".join(f"have={i}" for i in ids_of(ctx, *names))
    return url + (f"&match={match}" if match else "")


def test_kitchen_shows_my_ingredients_in_fridge_and_pantry(box, owner_client):
    page = owner_client.get("/ingredients").data.decode()
    assert "Fridge" in page and "Pantry" in page and "Fruits &amp; Vegetables" in page
    assert ">Chayote<" in page and ">Soy sauce<" in page
    assert "Pedro" not in page and "recipes found" not in page  # no search yet


def test_default_match_is_missing_one(box, ctx, owner_client):
    # Staples (salt) never count, so Sinangag is ready; Tinola misses chayote only.
    page = owner_client.get(picker_url(ctx, "chicken", "ginger", "garlic", "rice")).data.decode()
    assert "2 recipes found" in page and "Missing: chayote" in page and "Ready to cook" in page
    assert "Pedro" not in page
    assert 'value="missing1" selected' in page


def test_ready_to_cook_counts_staples_as_had(box, ctx, owner_client):
    page = owner_client.get(picker_url(ctx, "rice", "garlic", match="ready")).data.decode()
    assert "1 recipe found" in page and "Sinangag" in page and "Ready to cook" in page


def test_uses_all_and_any(box, ctx, owner_client):
    page = owner_client.get(picker_url(ctx, "chicken", "garlic", match="all")).data.decode()
    assert "1 recipe found" in page and "Uses: chicken, garlic" in page
    page = owner_client.get(picker_url(ctx, "chicken", "ginger", match="any")).data.decode()
    assert "2 recipes found" in page


def test_ids_that_arent_mine_are_ignored(box, ctx, owner_client, app, other_id):
    add_recipe(app, other_id, "Secret", ["1 cup lola's secret sauce"])
    secret = resolve(ctx, "lola's secret sauce")
    page = owner_client.get(f"/ingredients?have={secret.id}&have=abc&have=99999").data.decode()
    assert "Tap at least one ingredient first" in page and "Secret" not in page


def test_no_matches_offers_recipe_ideas(box, ctx, owner_client):
    page = owner_client.get(picker_url(ctx, "chayote", match="ready")).data.decode()
    assert "No Matches" in page and "/discover?have=chayote" in page


def test_bad_match_values_fall_back(box, ctx, owner_client):
    response = owner_client.get(picker_url(ctx, "rice") + "&match=nope")
    assert response.status_code == 200 and 'value="missing1" selected' in response.data.decode()


def test_old_search_links_redirect(box, ctx, owner_client):
    response = owner_client.get("/search?have=manok,+bawang&mode=pantry&missing=2")
    location = response.headers["Location"]
    assert response.status_code == 301 and location.startswith("/ingredients?")
    assert "match=missing2" in location and location.endswith("#results")
    assert all(f"have={i}" in location for i in ids_of(ctx, "chicken", "garlic"))
    response = owner_client.get("/search?q=adobo")
    assert response.status_code == 301 and response.headers["Location"] == "/?q=adobo"
