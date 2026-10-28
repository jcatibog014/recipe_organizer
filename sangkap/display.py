"""Get a recipe ready for the page: grouped ingredient lines, scaled amounts, emoji.

The same template shows your own recipes, shared ones (/r/...) and
TheMealDB ones (/discover/...), so the rows can be ORM objects or dicts.
"""
from .ingredients import EMOJI, emoji_for
from .quantities import format_quantity, scale

# A recipe without a photo gets a candy block with one emoji. Tags win first,
# in THIS order: what kind of dish it is (soup, noodles...) beats what's in it
# (pork, chicken...), so sinigang is a soup bowl, not bacon.
TAG_EMOJI = {
    "soup": "🍲", "sabaw": "🍲", "sinigang": "🍲", "noodles": "🍜", "pancit": "🍜", "pasta": "🍝",
    "stew": "🥘", "grill": "🍢", "grilled": "🍢", "bbq": "🍢", "inihaw": "🍢",
    "dessert": "🍮", "cake": "🍰", "baking": "🧁", "kakanin": "🍡", "drink": "🧋", "drinks": "🧋",
    "salad": "🥗", "bread": "🍞", "fried": "🍤", "prito": "🍤", "rice": "🍚", "sweets": "🍫",
    "merienda": "🍡", "snack": "🍡", "breakfast": "🍳",
    "seafood": "🦐", "fish": "🐟", "chicken": "🍗", "pork": "🥓", "beef": "🥩", "egg": "🥚",
    "vegetables": "🥬", "gulay": "🥬", "vegetarian": "🥬", "ulam": "🥘",
}
MAIN_KINDS = ("meat", "seafood")
BLOCK_COLOURS = 6  # .block-0 ... .block-5 in style.css


def value(row, name, default=None):
    """row.name for an object, row[name] for a dict."""
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def row_name(row):
    ingredient = value(row, "ingredient")
    return ingredient.name if ingredient is not None else value(row, "name", "")


def ingredient_groups(rows, factor=1.0):
    """Rows -> [{"section": "For the sauce", "lines": [...]}, ...], amounts scaled by factor."""
    groups = []
    for row in rows:
        section = value(row, "section", "") or ""
        if not groups or groups[-1]["section"] != section:
            groups.append({"section": section, "lines": []})
        name = row_name(row)
        ingredient = value(row, "ingredient")
        groups[-1]["lines"].append({
            "quantity": format_quantity(scale(value(row, "amount"), factor),
                                        scale(value(row, "amount_max"), factor),
                                        value(row, "unit", "") or ""),
            "name": name,
            "note": value(row, "note", "") or "",
            "optional": bool(value(row, "is_optional", False)),
            "emoji": emoji_for(name),
            "ingredient_id": ingredient.id if ingredient is not None else None,
        })
    return groups


def recipe_emoji(recipe):
    """The emoji for a recipe's candy block: from a tag, the main ingredient, or 🍲."""
    names = {tag if isinstance(tag, str) else tag.name for tag in value(recipe, "tags", []) or []}
    for name, emoji in TAG_EMOJI.items():
        if name in names:
            return emoji
    rows = value(recipe, "ingredients", []) or []
    for row in rows:
        ingredient = value(row, "ingredient")
        if ingredient is not None and ingredient.kind in MAIN_KINDS and ingredient.name in EMOJI:
            return EMOJI[ingredient.name]
    for row in rows:
        emoji = emoji_for(row_name(row))
        if emoji:
            return emoji
    return "🍲"


def block_class(recipe):
    key = value(recipe, "id") or len(value(recipe, "title", ""))
    return f"block-{int(key) % BLOCK_COLOURS}"


def servings_factor(recipe_servings, wanted):
    """How much to multiply amounts by: a recipe for 4 shown for 6 -> 1.5."""
    if not wanted or not recipe_servings:
        return 1.0
    return wanted / recipe_servings


def wanted_servings(text, default):
    """?servings=6 -> 6 (kept between 1 and 100); anything else -> default."""
    try:
        number = int(text)
    except (TypeError, ValueError):
        return default
    return max(1, min(100, number))
