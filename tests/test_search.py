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


def test_search_page_staples_box(box, owner_client):
    have = "/search?have=rice,garlic&mode=pantry&missing=0"
    assert "1 recipe found" in owner_client.get(have).data.decode()             # a link: staples on
    assert "1 recipe found" in owner_client.get(have + "&sent=1&staples=1").data.decode()
    assert "0 recipes found" in owner_client.get(have + "&sent=1").data.decode()  # box unticked


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


def test_search_page(app, box, owner_client):
    page = owner_client.get("/search?have=manok,+bawang&mode=all").data.decode()
    assert "1 recipe found" in page and "Adobo" in page and "Pedro" not in page
    assert "✓ chicken" in page


def test_search_page_unknown_ingredient(box, owner_client):
    page = owner_client.get("/search?have=unicorn").data.decode()
    assert "0 recipes found" in page and "unicorn" in page and "No matches" in page


def test_search_page_pantry_shows_what_is_missing(box, owner_client):
    page = owner_client.get("/search?have=chicken,ginger,garlic,rice&mode=pantry&missing=1").data.decode()
    assert "2 recipes found" in page and "✗ chayote" in page and "malunggay (optional)" in page


def test_bad_query_values_are_ignored(box, owner_client):
    response = owner_client.get("/search?mode=nope&missing=lots&time=7&tag=999")
    assert response.status_code == 200
