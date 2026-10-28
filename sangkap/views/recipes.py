"""Your recipes: the list (home page), one recipe, the add/edit form, photo, share, cook mode."""
import secrets

from flask import (
    Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for,
)
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from .. import db, ingredients, paste
from ..auth import login_required
from ..display import ingredient_groups, servings_factor, wanted_servings
from ..models import Photo, Recipe, RecipeIngredient, Step, Tag
from ..photos import PhotoError, process
from ..quantities import UNIT_CHOICES, amount_for_input
from ..validation import blank_row, rows_from_paste, validate_recipe
from . import owned_recipe

bp = Blueprint("recipes", __name__)

SORTS = {
    "new": ("Newest", (Recipe.created_at.desc(), Recipe.id.desc())),
    "az": ("A–Z", (func.lower(Recipe.title), Recipe.id)),
    "quick": ("Quickest", (func.coalesce(Recipe.prep_minutes, 0) + func.coalesce(Recipe.cook_minutes, 0),
                           Recipe.id)),
}
BLANK_ROWS = 4
BLANK_STEPS = 3
# The demo is shared by every visitor, so it can't fill the database.
DEMO_MAX_RECIPES = 60


def card_options():
    """What a recipe card needs, loaded in a few queries for the whole list (no N+1)."""
    return (
        selectinload(Recipe.tags),
        selectinload(Recipe.photo),
        selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient),
    )


@bp.get("/")
@login_required
def index():
    s = db.session()
    sort = request.args.get("sort", "new")
    if sort not in SORTS:
        sort = "new"
    favorites = request.args.get("favorites") == "1"
    tag_name = request.args.get("tag", "")

    query = select(Recipe).where(Recipe.user_id == g.user.id).options(*card_options())
    if favorites:
        query = query.where(Recipe.is_favorite.is_(True))
    if tag_name:
        query = query.where(Recipe.tags.any(Tag.name == tag_name))
    recipes = s.scalars(query.order_by(*SORTS[sort][1])).all()

    tags = s.scalars(select(Tag).where(Tag.user_id == g.user.id, Tag.recipes.any()).order_by(Tag.name)).all()
    total = s.scalar(select(func.count()).select_from(Recipe).where(Recipe.user_id == g.user.id))
    return render_template("recipes.html", recipes=recipes, tags=tags, sort=sort, sorts=SORTS,
                           favorites=favorites, tag_name=tag_name, total=total)


@bp.get("/recipes/<int:recipe_id>")
@login_required
def show(recipe_id):
    recipe = owned_recipe(recipe_id)
    servings = wanted_servings(request.args.get("servings"), recipe.servings)
    groups = ingredient_groups(recipe.ingredients, servings_factor(recipe.servings, servings))
    return render_template("recipe.html", recipe=recipe, groups=groups, servings=servings)


@bp.get("/recipes/<int:recipe_id>/cook")
@login_required
def cook(recipe_id):
    recipe = owned_recipe(recipe_id)
    servings = wanted_servings(request.args.get("servings"), recipe.servings)
    groups = ingredient_groups(recipe.ingredients, servings_factor(recipe.servings, servings))
    return render_template("cook.html", title=recipe.title, steps=[step.text for step in recipe.steps],
                           groups=groups, servings=servings,
                           back=url_for("recipes.show", recipe_id=recipe.id, servings=servings))


# ---------- Add and edit ----------

def form_rows_for(recipe):
    """The recipe's ingredient lines as form rows, with a heading row when the section changes."""
    rows = []
    section = ""
    for line in recipe.ingredients:
        if line.section != section:
            section = line.section
            heading = blank_row("section")
            heading["section"] = section
            rows.append(heading)
        row = blank_row()
        row.update(amount=amount_for_input(line.amount, line.amount_max), unit=line.unit,
                   name=line.ingredient.name, note=line.note, optional=line.is_optional)
        rows.append(row)
    return rows


def render_form(recipe, form_values, rows, steps, errors=None, status=200, message=None):
    return render_template(
        "recipe_form.html",
        recipe=recipe,
        form=form_values,
        rows=rows,
        steps=steps,
        errors=errors or {},
        unit_choices=UNIT_CHOICES,
        suggestions=ingredients.suggestions(db.session(), g.user.id),
        message=message,
        blank_row=blank_row(),
        blank_section=blank_row("section"),
    ), status


def save(recipe, data):
    """Copy checked form data onto the recipe (new or old). The caller commits."""
    s = db.session()
    for field in ("title", "description", "servings", "prep_minutes", "cook_minutes", "source_url", "notes"):
        setattr(recipe, field, data[field])

    tags = []
    for name in data["tags"]:
        tag = s.scalar(select(Tag).where(Tag.user_id == g.user.id, Tag.name == name))
        tags.append(tag or Tag(user_id=g.user.id, name=name))
    recipe.tags = tags  # the plain many-to-many: SQLAlchemy adds/removes recipe_tags rows

    # Find (or add) each catalog row first: get_or_create may flush the session,
    # and a half-built line must not be flushed.
    found = [ingredients.get_or_create(s, row["name"]) for row in data["rows"]]
    with s.no_autoflush:
        # The association objects: build the new list; delete-orphan removes the old rows.
        recipe.ingredients = [
            RecipeIngredient(
                ingredient=ingredient, amount=row["amount"], amount_max=row["amount_max"],
                unit=row["unit"], note=row["note"], is_optional=row["is_optional"],
                section=row["section"], position=position,
            )
            for position, (row, ingredient) in enumerate(zip(data["rows"], found))
        ]
        recipe.steps = [Step(text=text, position=position) for position, text in enumerate(data["steps"])]


def handle_form(recipe):
    """POST of the add/edit form: Save, More rows, or Paste ingredients."""
    data, errors = validate_recipe(request.form)
    form_values = request.form
    rows, steps = data["form_rows"], data["form_steps"]
    action = request.form.get("action", "save")

    if action == "more":
        return render_form(recipe, form_values, rows + [blank_row() for _ in range(3)], steps + [""])
    if action == "paste":
        pasted = rows_from_paste(paste.parse_block(request.form.get("paste", "")))
        kept = [row for row in rows if row["name"] or row["amount"] or row["section"]]
        message = (f"Added {len(pasted)} rows from your list. Check them, then save." if pasted
                   else "We couldn't find any ingredients in that text.")
        return render_form(recipe, form_values, kept + pasted + [blank_row()], steps or [""], message=message)

    if errors:
        return render_form(recipe, form_values, rows, steps or [""], errors=errors, status=400)

    s = db.session()
    if recipe is None:
        count = s.scalar(select(func.count()).select_from(Recipe).where(Recipe.user_id == g.user.id))
        if g.user.is_demo and count >= DEMO_MAX_RECIPES:
            abort(403, f"The demo can have up to {DEMO_MAX_RECIPES} recipes.")
        recipe = Recipe(user_id=g.user.id)
        s.add(recipe)
    save(recipe, data)
    upload = request.files.get("photo")
    if upload and upload.filename:
        try:
            set_photo(recipe, upload.read())
        except PhotoError as error:
            s.commit()
            flash(f"The recipe was saved, but the photo wasn't. {error}")
            return redirect(url_for("recipes.edit", recipe_id=recipe.id))
    s.commit()
    flash(f"Saved “{recipe.title}”.")
    return redirect(url_for("recipes.show", recipe_id=recipe.id))


@bp.route("/recipes/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        return handle_form(None)
    rows = [blank_row() for _ in range(BLANK_ROWS)]
    return render_form(None, {"servings": "4"}, rows, [""] * BLANK_STEPS)


@bp.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
@login_required
def edit(recipe_id):
    recipe = owned_recipe(recipe_id)
    if request.method == "POST":
        return handle_form(recipe)
    form_values = {
        "title": recipe.title, "description": recipe.description, "servings": str(recipe.servings),
        "prep_minutes": "" if recipe.prep_minutes is None else str(recipe.prep_minutes),
        "cook_minutes": "" if recipe.cook_minutes is None else str(recipe.cook_minutes),
        "source_url": recipe.source_url, "notes": recipe.notes,
        "tags": ", ".join(tag.name for tag in recipe.tags),
    }
    rows = form_rows_for(recipe) + [blank_row(), blank_row()]
    steps = [step.text for step in recipe.steps] + [""]
    return render_form(recipe, form_values, rows, steps)


@bp.post("/recipes/<int:recipe_id>/delete")
@login_required
def delete(recipe_id):
    recipe = owned_recipe(recipe_id)
    s = db.session()
    s.delete(recipe)  # cascades: its lines, steps, tag links, photo and plan entries go too
    s.commit()
    flash(f"Deleted “{recipe.title}”.")
    return redirect(url_for("recipes.index"))


@bp.post("/recipes/<int:recipe_id>/favorite")
@login_required
def favorite(recipe_id):
    recipe = owned_recipe(recipe_id)
    recipe.is_favorite = not recipe.is_favorite
    db.session().commit()
    return redirect(url_for("recipes.show", recipe_id=recipe.id))


@bp.post("/recipes/<int:recipe_id>/share")
@login_required
def share(recipe_id):
    """Turn the public link on (a new random code) or off."""
    recipe = owned_recipe(recipe_id)
    if recipe.share_code:
        recipe.share_code = None
        flash("Sharing is off. The old link no longer works.")
    else:
        # 9 random bytes = 12 letters: nobody can guess a link.
        recipe.share_code = secrets.token_urlsafe(9)
        flash("Sharing is on. Anyone with the link can read this recipe.")
    db.session().commit()
    return redirect(url_for("recipes.show", recipe_id=recipe.id) + "#share")


# ---------- Photo ----------

def set_photo(recipe, raw):
    """Resize the upload and keep it as the recipe's (only) photo. The caller commits."""
    data, width, height = process(raw)
    if recipe.photo is not None:
        db.session().delete(recipe.photo)
        db.session().flush()
    recipe.photo = Photo(data=data, mime="image/webp", width=width, height=height, size=len(data))


def photo_response(photo):
    if photo is None:
        abort(404)
    response = Response(photo.data, mimetype=photo.mime)
    # The address has ?v=<photo id>, and a new photo gets a new id,
    # so the browser can keep this one for a long time.
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return response


@bp.get("/recipes/<int:recipe_id>/photo")
@login_required
def photo(recipe_id):
    return photo_response(owned_recipe(recipe_id).photo)


@bp.post("/recipes/<int:recipe_id>/photo/delete")
@login_required
def delete_photo(recipe_id):
    recipe = owned_recipe(recipe_id)
    if recipe.photo is not None:
        recipe.photo = None
        db.session().commit()
        flash("The photo has been removed.")
    return redirect(url_for("recipes.edit", recipe_id=recipe.id))
