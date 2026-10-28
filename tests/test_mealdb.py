"""TheMealDB: our code against saved answers (tests/fixtures/mealdb/), never the internet."""
import json

import pytest

from sangkap import mealdb

from conftest import FIXTURES


def bistek():
    return json.loads((FIXTURES / "lookup_53069.json").read_text(encoding="utf-8"))["meals"][0]


def test_flat_row_becomes_our_shape():
    recipe = mealdb.to_recipe(bistek())
    assert recipe["title"] == "Bistek"
    assert recipe["tags"] == ["filipino", "beef"]
    assert recipe["servings"] == mealdb.DEFAULT_SERVINGS
    rows = {row["name"]: (row["amount"], row["unit"], row["note"]) for row in recipe["ingredients"]}
    assert rows["beef"] == (1.0, "lb", "")
    assert rows["soy sauce"] == (5.0, "tbsp", "")      # "5 tablespoons"
    assert rows["garlic"] == (3.0, "clove", "")
    assert rows["olive oil"] == (4.0, "tbsp", "")      # "4 tbs"
    assert rows["salt"] == (1.0, "pinch", "")
    assert rows["onion"] == (3.0, "", "parts")         # "3 parts": not a unit we know, so a note
    assert len(recipe["ingredients"]) == 8             # the empty slots 9-20 are skipped


def test_steps_lose_their_numbers():
    steps = mealdb.to_recipe(bistek())["steps"]
    assert steps[0].startswith("Marinate beef in soy sauce")
    assert not any(step[0].isdigit() and step[1:3] in (".\t", ". ") for step in steps)


@pytest.mark.parametrize("text, expected", [
    ("STEP 1\r\nBoil water.\r\n\r\nSTEP 2\r\nAdd rice.", ["Boil water.", "Add rice."]),
    ("1. Chop.\n2) Fry.\n- Serve.", ["Chop.", "Fry.", "Serve."]),
    ("", []),
])
def test_split_steps(text, expected):
    assert mealdb.split_steps(text) == expected


def test_one_huge_paragraph_is_split():
    text = " ".join(f"Sentence number {i} is here." for i in range(30))
    steps = mealdb.split_steps(text)
    assert len(steps) == 15 and steps[0] == "Sentence number 0 is here. Sentence number 1 is here."


def test_measures_we_cant_read_become_notes():
    meal = {"idMeal": "1", "strMeal": "X", "strIngredient1": "Salt", "strMeasure1": "To taste",
            "strIngredient2": "Eggs", "strMeasure2": "2 Large", "strIngredient3": " ", "strMeasure3": "1 cup"}
    rows = mealdb.to_recipe(meal)["ingredients"]
    assert [(r["name"], r["amount"], r["note"]) for r in rows] == [("salt", None, "To taste"),
                                                                    ("eggs", 2.0, "Large")]


def test_pictures_only_from_themealdb():
    assert mealdb.image_url({"strMealThumb": "https://www.themealdb.com/images/x.jpg"}, "small") == \
        "https://www.themealdb.com/images/x.jpg/small"
    assert mealdb.image_url({"strMealThumb": "https://evil.example/x.jpg"}) == ""


def test_lists():
    assert "Filipino" in mealdb.list_areas()
    assert mealdb.by_area("Filipino")[0] == {
        "id": "53071", "name": "Beef Asado",
        "thumb": "https://www.themealdb.com/images/media/meals/pkopc31683207947.jpg"}
    assert mealdb.lookup("abc") is None
    assert mealdb.lookup("99999") is None


def test_best_name_uses_aliases_themealdb_knows():
    assert mealdb.best_name(["eggplant", "talong", "aubergine"]) == "aubergine"
    assert mealdb.best_name(["garlic", "bawang"]) == "garlic"
    assert mealdb.best_name(["kangkong"]) == "kangkong"


def test_several_ingredients_keep_meals_in_every_answer(monkeypatch):
    answers = {
        "a": {"meals": [{"idMeal": "1", "strMeal": "One"}, {"idMeal": "2", "strMeal": "Two"}]},
        "b": {"meals": [{"idMeal": "2", "strMeal": "Two"}, {"idMeal": "3", "strMeal": "Three"}]},
    }
    monkeypatch.setattr(mealdb, "FETCH_JSON", lambda url: answers.get(url[-1], {"meals": []}))
    monkeypatch.setattr(mealdb, "best_name", lambda candidates: candidates[0])
    assert [m["name"] for m in mealdb.by_ingredients([["a"], ["b"]])] == ["Two"]


def test_answers_are_cached(offline_mealdb):
    mealdb.by_area("Filipino")
    mealdb.by_area("Filipino")
    assert len(offline_mealdb) == 1


def test_network_trouble_becomes_mealdb_error(monkeypatch):
    def broken(url):
        raise OSError("no internet")
    monkeypatch.setattr(mealdb, "FETCH_JSON", broken)
    with pytest.raises(mealdb.MealDBError):
        mealdb.search_name("adobo")
