"""Shared recipes: /r/<code> is readable by anyone with the link, no login.

Only recipes with sharing turned on have a share_code. The page leaves out
the owner's name and private notes, and asks search engines not to list it.
Turning sharing off (or on again, with a new code) makes old links 404.
"""
from flask import Blueprint, abort, make_response, render_template, request, url_for
from sqlalchemy import select

from .. import db
from ..display import ingredient_groups, servings_factor, wanted_servings
from ..models import Recipe
from .recipes import photo_response

bp = Blueprint("shared", __name__)


def shared_recipe(code):
    recipe = db.session().scalar(select(Recipe).where(Recipe.share_code == code))
    if recipe is None:
        abort(404)
    return recipe


def noindex(response):
    response = make_response(response)
    response.headers["X-Robots-Tag"] = "noindex"
    return response


def scaled(recipe):
    servings = wanted_servings(request.args.get("servings"), recipe.servings)
    return servings, ingredient_groups(recipe.ingredients, servings_factor(recipe.servings, servings))


@bp.get("/r/<code>")
def show(code):
    recipe = shared_recipe(code)
    servings, groups = scaled(recipe)
    photo_url = url_for("shared.photo", code=code, v=recipe.photo.id) if recipe.photo else None
    return noindex(render_template("shared.html", recipe=recipe, groups=groups, servings=servings,
                                   photo_url=photo_url, code=code))


@bp.get("/r/<code>/cook")
def cook(code):
    recipe = shared_recipe(code)
    servings, groups = scaled(recipe)
    return noindex(render_template(
        "cook.html", title=recipe.title, steps=[step.text for step in recipe.steps], groups=groups,
        servings=servings, back=url_for("shared.show", code=code, servings=servings), noindex=True))


@bp.get("/r/<code>/photo")
def photo(code):
    return noindex(photo_response(shared_recipe(code).photo))
