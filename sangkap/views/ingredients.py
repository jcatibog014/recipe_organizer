"""The "What can I cook?" page: pick what's in your fridge and pantry, then find recipes.

Also the ingredient list for managing (recipe counts, rename/merge).
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from .. import db, ingredients, search
from ..auth import login_required
from ..models import Ingredient, Recipe, RecipeIngredient
from .recipes import card_options

bp = Blueprint("ingredients", __name__)

# Where each kind of ingredient lives in the picture.
FRIDGE_SHELVES = ("meat", "seafood", "dairy")
CRISPER = "produce"  # the fridge's bottom drawer
PANTRY_SHELVES = ("pantry", "spice", "other")


def by_shelf(usage):
    """[(ingredient, count)] -> {kind: [ingredients A-Z]} (only kinds you have)."""
    shelves = {}
    for ingredient, _count in usage:
        kind = ingredient.kind if ingredient.kind in ingredients.KINDS else "other"
        shelves.setdefault(kind, []).append(ingredient)
    for items in shelves.values():
        items.sort(key=lambda ingredient: ingredient.name)
    return shelves


@bp.get("/ingredients")
@login_required
def index():
    """Tap what you have, press Find recipes: ?have=<id>&have=<id>&match=missing1."""
    s = db.session()
    usage = ingredients.usage(s, g.user.id)
    mine = {ingredient.id: ingredient for ingredient, _count in usage}

    # Only ids of ingredients in your own recipes count; anything else is ignored.
    picked = []
    for value in request.args.getlist("have"):
        if value.isdigit() and int(value) in mine and int(value) not in picked:
            picked.append(int(value))
    match = request.args.get("match", search.DEFAULT_MATCH)
    if match not in search.MATCHES:
        match = search.DEFAULT_MATCH
    _label, mode, missing_max = search.MATCHES[match]

    searched = "have" in request.args or "match" in request.args
    results = []
    if picked:
        query = search.Query(
            have=picked, mode=mode, missing_max=missing_max,
            # Water, salt, oil and pepper never count as missing.
            staples=search.resolve_staples(s) if mode == "pantry" else [],
        )
        results = search.run(s, g.user.id, query)

    return render_template(
        "ingredients.html", shelves=by_shelf(usage), fridge_shelves=FRIDGE_SHELVES, crisper=CRISPER,
        pantry_shelves=PANTRY_SHELVES, picked=picked, picked_names=[mine[i].name for i in picked],
        match=match, matches=search.MATCHES, mode=mode, searched=searched, results=results,
    )


@bp.get("/ingredients/manage")
@login_required
def manage():
    """Your ingredients with how many recipes use each; open one to rename or merge it."""
    usage = ingredients.usage(db.session(), g.user.id)
    groups = {kind: [] for kind in ingredients.KINDS}
    for ingredient, count in usage:
        groups.setdefault(ingredient.kind, []).append((ingredient, count))
    for rows in groups.values():
        rows.sort(key=lambda row: row[0].name)
    return render_template("ingredients_manage.html", groups=groups, total=len(usage))


def visible_ingredient(ingredient_id):
    """A starter ingredient, or one that your recipes use. Others' new names stay hidden (404)."""
    s = db.session()
    ingredient = s.get(Ingredient, ingredient_id)
    if ingredient is None:
        abort(404)
    mine = s.scalar(
        select(func.count()).select_from(RecipeIngredient).join(Recipe)
        .where(RecipeIngredient.ingredient_id == ingredient.id, Recipe.user_id == g.user.id)
    )
    if not ingredient.is_seeded and not mine:
        abort(404)
    return ingredient


@bp.get("/ingredients/<int:ingredient_id>")
@login_required
def show(ingredient_id):
    ingredient = visible_ingredient(ingredient_id)
    recipes = db.session().scalars(
        select(Recipe)
        .where(Recipe.user_id == g.user.id,
               Recipe.ingredients.any(RecipeIngredient.ingredient_id == ingredient.id))
        .options(*card_options())
        .order_by(Recipe.title)
    ).all()
    return render_template("ingredient.html", ingredient=ingredient, recipes=recipes,
                           suggestions=ingredients.suggestions(db.session(), g.user.id))


@bp.post("/ingredients/<int:ingredient_id>/merge")
@login_required
def merge(ingredient_id):
    """Rename this ingredient in your recipes, or merge it into another one."""
    source = visible_ingredient(ingredient_id)
    target_name = ingredients.normalize(request.form.get("target", ""))
    if not target_name:
        flash("Enter a new name first.")
        return redirect(url_for("ingredients.show", ingredient_id=source.id))
    s = db.session()
    # The demo is shared by everyone, so it can't add aliases to the shared catalog.
    target, moved = ingredients.merge(s, g.user.id, source, target_name, keep_alias=not g.user.is_demo)
    s.commit()
    if moved:
        flash(f"Moved {moved} ingredient line{'s' if moved != 1 else ''} from “{source.name}” to “{target.name}”.")
    else:
        flash("Nothing needed to change.")
    return redirect(url_for("ingredients.show", ingredient_id=target.id))
