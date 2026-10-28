from werkzeug.datastructures import MultiDict

from sangkap.validation import parse_tags, validate_recipe


def recipe_form(**fields):
    base = {"title": "Rice", "servings": "4"}
    base.update(fields)
    return MultiDict([(k, v) for k, values in base.items()
                      for v in (values if isinstance(values, list) else [values])])


def test_minimal_recipe_is_fine():
    data, errors = validate_recipe(recipe_form())
    assert errors == {}
    assert (data["title"], data["servings"], data["rows"], data["steps"]) == ("Rice", 4, [], [])


def test_numbers_are_checked():
    _data, errors = validate_recipe(recipe_form(servings="0", prep_minutes="abc", cook_minutes="99999"))
    assert set(errors) == {"servings", "prep_minutes", "cook_minutes"}


def test_source_url_must_be_a_web_address():
    _data, errors = validate_recipe(recipe_form(source_url="javascript:alert(1)"))
    assert "source_url" in errors
    _data, errors = validate_recipe(recipe_form(source_url="https://panlasangpinoy.com/adobo"))
    assert errors == {}


def test_blank_rows_are_skipped_and_sections_carry_over():
    form = recipe_form(row_kind=["item", "section", "item", "item"], row_section=["", "Sauce", "", ""],
                       row_amount=["", "", "2", ""], row_unit=["", "", "tbsp", ""],
                       row_name=["", "", "soy sauce", ""], row_note=["", "", "", ""],
                       row_optional=["", "", "1", ""])
    data, errors = validate_recipe(form)
    assert errors == {}
    assert data["rows"] == [{"section": "Sauce", "amount": 2.0, "amount_max": None, "unit": "tbsp",
                             "name": "soy sauce", "note": "", "is_optional": True}]


def test_a_row_needs_a_name_and_a_real_unit():
    form = recipe_form(row_kind=["item", "item"], row_section=["", ""], row_amount=["2", "1"],
                       row_unit=["", "bucket"], row_name=["", "rice"], row_note=["", ""], row_optional=["", ""])
    data, errors = validate_recipe(form)
    assert "rows" in errors
    assert [row["error"] for row in data["form_rows"]] == ["Write what the ingredient is.",
                                                           "Choose a unit from the list."]


def test_tags():
    assert parse_tags(" Soup, #Quick ,soup,, Party  Food ") == ["soup", "quick", "party food"]
    _data, errors = validate_recipe(recipe_form(tags=",".join(f"t{i}" for i in range(13))))
    assert "tags" in errors
