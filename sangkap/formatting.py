"""Small text helpers for the templates (Jinja filters). No Flask needed to test them."""
from .display import block_class, recipe_emoji
from .ingredients import KIND_LABELS, emoji_for


def minutes(total):
    """75 -> "1 hr 15 min", 30 -> "30 min", None -> "". """
    if not total:
        return ""
    hours, mins = divmod(int(total), 60)
    if hours and mins:
        return f"{hours} hr {mins} min"
    if hours:
        return f"{hours} hr"
    return f"{mins} min"


def plural(count, word, many=None):
    """plural(1, "recipe") -> "1 recipe", plural(3, "recipe") -> "3 recipes"."""
    return f"{count} {word if count == 1 else (many or word + 's')}"


def init_app(app):
    app.jinja_env.filters["minutes"] = minutes
    app.jinja_env.filters["emoji"] = emoji_for
    app.jinja_env.globals.update(
        plural=plural,
        recipe_emoji=recipe_emoji,
        block_class=block_class,
        KIND_LABELS=KIND_LABELS,
        # The tabs only show pages that exist (has_page("search.index")).
        has_page=lambda endpoint: endpoint in app.view_functions,
    )
