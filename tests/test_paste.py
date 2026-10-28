from sangkap.paste import parse_block, parse_line


def item(**kwargs):
    row = {"kind": "item", "amount": None, "amount_max": None, "unit": "", "name": "", "note": "",
           "is_optional": False}
    row.update(kwargs)
    return row


def test_amount_unit_name_note():
    assert parse_line("3 cloves garlic, minced") == item(amount=3.0, unit="clove", name="garlic", note="minced")


def test_brackets_become_the_note():
    assert parse_line("1 ½ cups coconut milk (gata)") == item(amount=1.5, unit="cup", name="coconut milk",
                                                              note="gata")


def test_optional_and_range():
    assert parse_line("2-3 pcs siling labuyo (optional)") == item(
        amount=2.0, amount_max=3.0, unit="pc", name="siling labuyo", is_optional=True)


def test_to_taste_has_no_amount():
    assert parse_line("salt to taste") == item(name="salt", note="to taste")
    assert parse_line("Pepper, to taste") == item(name="Pepper", note="to taste")


def test_bullets_and_numbers_are_removed():
    assert parse_line("- 1 kg chicken")["name"] == "chicken"
    assert parse_line("• 2 eggs")["amount"] == 2.0
    assert parse_line("3) 1 tbsp oil")["unit"] == "tbsp"


def test_heading():
    assert parse_line("For the sauce:") == {"kind": "section", "section": "For the sauce"}


def test_blank_line():
    assert parse_line("   ") is None


def test_block_keeps_order_and_headings():
    rows = parse_block("""
        1 kg pork belly

        For the sauce:
        1/2 cup soy sauce
        6 cloves garlic, crushed
    """)
    assert [row.get("name") or row.get("section") for row in rows] == [
        "pork belly", "For the sauce", "soy sauce", "garlic"]
    assert rows[2]["amount"] == 0.5


def test_no_amount_no_unit_word_is_the_name():
    assert parse_line("2 large eggs") == item(amount=2.0, name="large eggs")
