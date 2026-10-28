import pytest

from sangkap.quantities import (
    amount_for_input, canonical_unit, format_number, format_quantity, parse_amount, parse_number,
    split_quantity,
)


@pytest.mark.parametrize("text, expected", [
    ("2", 2.0), ("1.5", 1.5), ("1/2", 0.5), ("1 1/2", 1.5), ("1½", 1.5), ("1 ½", 1.5), ("½", 0.5),
    ("3/2", 1.5), ("  2  ", 2.0),
])
def test_parse_number(text, expected):
    assert parse_number(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "1/0", "1 2 3", "1,5", "-2"])
def test_parse_number_rejects(text):
    assert parse_number(text) is None


@pytest.mark.parametrize("text, expected", [
    ("", (None, None)),
    ("2", (2.0, None)),
    ("2-3", (2.0, 3.0)),
    ("2 – 3", (2.0, 3.0)),
    ("2 to 3", (2.0, 3.0)),
    ("1/2-1", (0.5, 1.0)),
    ("2-2", (2.0, None)),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text, message", [
    ("lots", "Write an amount"),
    ("0", "more than 0"),
    ("3-2", "smaller number first"),
    ("999999", "too big"),
])
def test_parse_amount_errors(text, message):
    with pytest.raises(ValueError, match=message):
        parse_amount(text)


@pytest.mark.parametrize("value, expected", [
    (1.5, "1 ½"), (0.5, "½"), (1 / 3, "⅓"), (2 / 3, "⅔"), (0.25, "¼"), (2.75, "2 ¾"),
    (0.125, "⅛"), (2, "2"), (2.999, "3"), (2.7, "2.7"), (1250, "1250"), (None, ""),
])
def test_format_number(value, expected):
    assert format_number(value) == expected


def test_format_quantity():
    assert format_quantity(1.5, None, "cup") == "1 ½ cups"
    assert format_quantity(1, None, "cup") == "1 cup"
    assert format_quantity(2, 3, "clove") == "2–3 cloves"
    assert format_quantity(3, None, "") == "3"
    assert format_quantity(None, None, "") == ""
    assert format_quantity(None, None, "pinch") == "pinch"
    assert format_quantity(500, None, "g") == "500 g"


def test_scaling_a_third_stays_a_fraction():
    # 1/3 cup for 4 people, shown for 2 -> 1/6 is not "nice", 1/3 x 3 = 1
    assert format_quantity((1 / 3) * 3, None, "cup") == "1 cup"
    assert format_quantity((1 / 2) * 1.5, None, "tsp") == "¾ tsp"


@pytest.mark.parametrize("word, unit", [
    ("Tablespoons", "tbsp"), ("tbs", "tbsp"), ("tsp.", "tsp"), ("grams", "g"), ("pcs", "pc"),
    ("cloves", "clove"), ("thumb-sized", "thumb"), ("L", "l"), ("rice", None),
])
def test_canonical_unit(word, unit):
    assert canonical_unit(word) == unit


@pytest.mark.parametrize("text, expected", [
    ("1 ½ cups rice", (1.5, None, "cup", "rice")),
    ("500g pork", (500.0, None, "g", "pork")),
    ("2-3 cloves", (2.0, 3.0, "clove", "")),
    ("1 cup of rice", (1.0, None, "cup", "rice")),
    ("2 tomatoes", (2.0, None, "", "tomatoes")),
    ("salt", (None, None, "", "salt")),
    ("pinch of salt", (None, None, "pinch", "salt")),
    ("cup", (None, None, "", "cup")),  # a unit word with no amount isn't a unit
])
def test_split_quantity(text, expected):
    assert split_quantity(text) == expected


def test_amount_for_input_round_trips():
    for amount, amount_max in [(1.5, None), (0.25, None), (2, 3), (None, None), (2.7, None)]:
        assert parse_amount(amount_for_input(amount, amount_max)) == (
            pytest.approx(amount) if amount else None, amount_max)
