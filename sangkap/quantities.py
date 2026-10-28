"""Amounts and units: read "1 ½", "2-3", "1/4"; show 1.5 as "1 ½"; scale.

Amounts are stored as numbers (1.5), not text ("1 1/2"), so a recipe for
4 can be shown for 6, and the shopping list can add amounts up.
Plain Python, no Flask and no database (see tests/test_quantities.py).
"""
import re

MAX_AMOUNT = 100_000

# Our units, in the order the form shows them: unit -> (one, many).
UNITS = {
    "g": ("g", "g"),
    "kg": ("kg", "kg"),
    "ml": ("ml", "ml"),
    "l": ("L", "L"),
    "cup": ("cup", "cups"),
    "tbsp": ("tbsp", "tbsp"),
    "tsp": ("tsp", "tsp"),
    "pc": ("pc", "pcs"),
    "clove": ("clove", "cloves"),
    "slice": ("slice", "slices"),
    "can": ("can", "cans"),
    "pack": ("pack", "packs"),
    "sachet": ("sachet", "sachets"),
    "bottle": ("bottle", "bottles"),
    "bunch": ("bunch", "bunches"),
    "head": ("head", "heads"),
    "stalk": ("stalk", "stalks"),
    "sprig": ("sprig", "sprigs"),
    "thumb": ("thumb", "thumbs"),
    "stick": ("stick", "sticks"),
    "handful": ("handful", "handfuls"),
    "pinch": ("pinch", "pinches"),
    "dash": ("dash", "dashes"),
    "lb": ("lb", "lb"),
    "oz": ("oz", "oz"),
}

# Other ways people write them. Keys are lower-case, without a final ".".
UNIT_ALIASES = {
    "gram": "g", "grams": "g", "gr": "g", "grm": "g",
    "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "mls": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml", "cc": "ml",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l", "ltr": "l",
    "cups": "cup",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbs": "tbsp", "tbsps": "tbsp", "tbl": "tbsp", "tblsp": "tbsp",
    "teaspoon": "tsp", "teaspoons": "tsp", "tsps": "tsp",
    "pcs": "pc", "piece": "pc", "pieces": "pc",
    "cloves": "clove",
    "slices": "slice",
    "cans": "can", "tin": "can", "tins": "can",
    "packs": "pack", "packet": "pack", "packets": "pack", "pouch": "pack",
    "sachets": "sachet",
    "bottles": "bottle",
    "bunches": "bunch", "tali": "bunch",
    "heads": "head",
    "stalks": "stalk",
    "sprigs": "sprig",
    "thumbs": "thumb", "thumb-sized": "thumb", "thumb-size": "thumb",
    "sticks": "stick",
    "handfuls": "handful",
    "pinches": "pinch",
    "dashes": "dash",
    "lbs": "lb", "pound": "lb", "pounds": "lb",
    "ounce": "oz", "ounces": "oz",
}

# For the form's <select>: (value, label). "" means "no unit" ("3 eggs").
UNIT_CHOICES = [("", "—")] + [(unit, labels[0]) for unit, labels in UNITS.items()]

# Units that can be turned into each other, as (family, size in the base unit).
CONVERSIONS = {
    "g": ("mass", 1), "kg": ("mass", 1000), "lb": ("mass", 453.6), "oz": ("mass", 28.35),
    "ml": ("volume", 1), "l": ("volume", 1000), "cup": ("volume", 240),
    "tbsp": ("volume", 15), "tsp": ("volume", 5),
}

UNICODE_FRACTIONS = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8", "⅕": "1/5",
}

# Fractions we show, as (value, sign). Anything else shows as a decimal.
NICE_FRACTIONS = [
    (1 / 8, "⅛"), (1 / 4, "¼"), (1 / 3, "⅓"), (3 / 8, "⅜"), (1 / 2, "½"),
    (5 / 8, "⅝"), (2 / 3, "⅔"), (3 / 4, "¾"), (7 / 8, "⅞"),
]

NUMBER_CHARS = "0-9½⅓⅔¼¾⅛⅜⅝⅞⅕"
# One amount: "2", "1.5", "1/2", "1 1/2", "1 ½", "1½", "½".
AMOUNT = rf"[{NUMBER_CHARS}][{NUMBER_CHARS}./]*(?:\s+(?:\d+/\d+|[½⅓⅔¼¾⅛⅜⅝⅞⅕]))?"
# An amount or a range at the start of a text: "2-3", "2 to 3", "1 ½".
LEADING_AMOUNT = re.compile(rf"^\s*(?P<amount>{AMOUNT}(?:\s*(?:-|–|—|to)\s*{AMOUNT})?)\s*", re.IGNORECASE)
RANGE_SPLIT = re.compile(r"\s*(?:-|–|—|\bto\b)\s*", re.IGNORECASE)


def canonical_unit(word):
    """ "Tablespoons" -> "tbsp", "g" -> "g", "handful" -> "handful", "rice" -> None."""
    word = (word or "").strip().lower().rstrip(".")
    if word in UNITS:
        return word
    return UNIT_ALIASES.get(word)


def parse_number(text):
    """One number: "1 1/2", "1½", "1.5" and "3/2" all give 1.5. None if it isn't one."""
    text = (text or "").strip()
    for sign, fraction in UNICODE_FRACTIONS.items():
        text = text.replace(sign, f" {fraction}")
    parts = text.split()
    if not 1 <= len(parts) <= 2:
        return None
    total = 0.0
    for part in parts:
        if re.fullmatch(r"\d+(?:\.\d+)?", part):
            total += float(part)
        elif re.fullmatch(r"\d+/\d+", part):
            top, bottom = part.split("/")
            if int(bottom) == 0:
                return None
            total += int(top) / int(bottom)
        else:
            return None
    return total


def parse_amount(text):
    """Read what someone typed in the amount box.

    Returns (amount, amount_max): "" -> (None, None) ("to taste"),
    "2" -> (2.0, None), "2-3" -> (2.0, 3.0). Raises ValueError with a
    message for the form when it can't be read.
    """
    text = (text or "").strip()
    if not text:
        return None, None
    parts = RANGE_SPLIT.split(text, maxsplit=1)
    numbers = [parse_number(part) for part in parts]
    if any(number is None for number in numbers):
        raise ValueError("Write an amount like 2, 1.5, 1/2, 1 1/2 or 2-3.")
    low = numbers[0]
    high = numbers[1] if len(numbers) == 2 else None
    if low <= 0 or (high is not None and high <= 0):
        raise ValueError("The amount must be more than 0.")
    if max(low, high or 0) > MAX_AMOUNT:
        raise ValueError("That amount is too big.")
    if high is not None:
        if high < low:
            raise ValueError("In a range, write the smaller number first (2-3).")
        if high == low:
            high = None
    return low, high


def split_quantity(text):
    """Take the amount and unit off the front of a text.

    "1 ½ cups rice" -> (1.5, None, "cup", "rice")
    "500g pork"     -> (500.0, None, "g", "pork")
    "2-3 cloves"    -> (2.0, 3.0, "clove", "")
    "salt"          -> (None, None, "", "salt")
    """
    text = (text or "").strip()
    amount = amount_max = None
    match = LEADING_AMOUNT.match(text)
    if match:
        try:
            amount, amount_max = parse_amount(match.group("amount"))
            text = text[match.end():]
        except ValueError:
            pass
    unit = ""
    word, _space, rest = text.partition(" ")
    found = canonical_unit(word)
    if found and (amount is not None or found in ("pinch", "dash", "handful")):
        unit, text = found, rest
    if unit and text.lower().startswith("of "):  # "1 cup of rice"
        text = text[3:]
    return amount, amount_max, unit, text.strip()


def format_number(value):
    """1.5 -> "1 ½", 0.333 -> "⅓", 2 -> "2", 2.7 -> "2.7", 1250 -> "1250"."""
    if value is None:
        return ""
    if value >= 100:
        return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}"
    whole = int(value)
    rest = value - whole
    if rest < 0.02:
        return str(whole)
    if rest > 0.98:
        return str(whole + 1)
    for fraction, sign in NICE_FRACTIONS:
        if abs(rest - fraction) < 0.02:
            return f"{whole} {sign}" if whole else sign
    return f"{value:.2f}".rstrip("0").rstrip(".")


def unit_label(unit, amount):
    """The unit as shown: "cup" for 1, "cups" for 2."""
    if not unit:
        return ""
    one, many = UNITS.get(unit, (unit, unit))
    return many if amount is not None and amount > 1.02 else one


def format_quantity(amount, amount_max=None, unit=""):
    """ (1.5, None, "cup") -> "1 ½ cups";  (2, 3, "clove") -> "2–3 cloves";  (None, None, "") -> "". """
    if amount is None:
        return unit_label(unit, None)  # "pinch", or "" for "to taste"
    text = format_number(amount)
    if amount_max is not None:
        text += "–" + format_number(amount_max)
    label = unit_label(unit, amount_max if amount_max is not None else amount)
    return f"{text} {label}" if label else text


def amount_for_input(amount, amount_max=None):
    """What the amount box shows when editing: 1.5 -> "1 1/2", (2, 3) -> "2-3"."""
    def plain(value):
        text = format_number(value)
        for sign, fraction in UNICODE_FRACTIONS.items():
            text = text.replace(sign, fraction)
        return text
    if amount is None:
        return ""
    return plain(amount) + (f"-{plain(amount_max)}" if amount_max is not None else "")


def scale(amount, factor):
    return None if amount is None else amount * factor
