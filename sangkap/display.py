"""Get a recipe ready for the page: grouped ingredient lines and scaled amounts.

The same template shows your own recipes, shared ones (/r/...) and
TheMealDB ones (/discover/...), so the rows can be ORM objects or dicts.
"""
from .quantities import format_quantity, scale

ACCENT_COLOURS = 6  # .accent-0 ... .accent-5 in style.css


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
        ingredient = value(row, "ingredient")
        groups[-1]["lines"].append({
            "quantity": format_quantity(scale(value(row, "amount"), factor),
                                        scale(value(row, "amount_max"), factor),
                                        value(row, "unit", "") or ""),
            "name": row_name(row),
            "note": value(row, "note", "") or "",
            "optional": bool(value(row, "is_optional", False)),
            "ingredient_id": ingredient.id if ingredient is not None else None,
        })
    return groups


def accent_class(recipe):
    """The candy colour of a card's top strip: steady per recipe, varied across the grid."""
    key = value(recipe, "id") or len(value(recipe, "title", ""))
    return f"accent-{int(key) % ACCENT_COLOURS}"


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
