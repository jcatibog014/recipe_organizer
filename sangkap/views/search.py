"""The old search page (/search). Searching now lives on two pages:

- "What Can I Cook?" (/ingredients) for the ingredients you have,
- My Recipes (/?q=...) for recipe names.

Old bookmarks still work: /search sends you to the right one.
"""
from flask import Blueprint, redirect, request, url_for

from .. import db, ingredients, search
from ..auth import login_required

bp = Blueprint("search", __name__)

# Old mode/missing values -> the new "Match" menu.
OLD_MATCH = {"all": "all", "any": "any"}
OLD_MISSING = {"0": "ready", "1": "missing1", "2": "missing2", "3": "missing2"}


@bp.get("/search")
@login_required
def index():
    have = search.split_names(request.args.get("have"))
    if have:
        s = db.session()
        ids = []
        for name in have:
            ingredient = ingredients.resolve(s, name)
            if ingredient is not None and ingredient.id not in ids:
                ids.append(ingredient.id)
        mode = request.args.get("mode", "all")
        match = OLD_MATCH.get(mode) or OLD_MISSING.get(request.args.get("missing", "1"), "missing1")
        return redirect(url_for("ingredients.index", have=ids, match=match, _anchor="results"), 301)
    return redirect(url_for("recipes.index", q=request.args.get("q") or None), 301)
