"""The pages, one blueprint per part of the app, plus helpers they share."""
from flask import abort, g

from .. import db
from ..models import Recipe


def owned_recipe(recipe_id):
    """The recipe with this id, if it belongs to the logged-in user. Otherwise 404.

    We answer "not found" (and not "forbidden") for other people's recipes,
    so nobody can find out which ids exist.
    """
    recipe = db.session().get(Recipe, recipe_id)
    if recipe is None or recipe.user_id != g.user.id:
        abort(404)
    return recipe
