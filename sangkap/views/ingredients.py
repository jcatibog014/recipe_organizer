"""Your ingredients: how many recipes use each, and rename/merge."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from .. import db, ingredients
from ..auth import login_required
from ..models import Ingredient, Recipe, RecipeIngredient
from .recipes import card_options

bp = Blueprint("ingredients", __name__)


@bp.get("/ingredients")
@login_required
def index():
    usage = ingredients.usage(db.session(), g.user.id)
    groups = {kind: [] for kind in ingredients.KINDS}
    for ingredient, count in usage:
        groups.setdefault(ingredient.kind, []).append((ingredient, count))
    for rows in groups.values():
        rows.sort(key=lambda row: row[0].name)
    return render_template("ingredients.html", groups=groups, total=len(usage))


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
        flash("Write the new name first.")
        return redirect(url_for("ingredients.show", ingredient_id=source.id))
    s = db.session()
    # The demo is shared by everyone, so it can't add aliases to the shared catalog.
    target, moved = ingredients.merge(s, g.user.id, source, target_name, keep_alias=not g.user.is_demo)
    s.commit()
    if moved:
        flash(f"Moved {moved} ingredient line{'s' if moved != 1 else ''} from “{source.name}” to “{target.name}”. ✨")
    else:
        flash("Nothing to change.")
    return redirect(url_for("ingredients.show", ingredient_id=target.id))
