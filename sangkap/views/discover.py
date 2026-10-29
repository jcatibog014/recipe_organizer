"""Recipe ideas (the code calls it "discover"): ready-made recipes from TheMealDB
to cook right away or save."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from .. import db, ingredients, mealdb, search
from ..auth import login_required
from ..display import ingredient_groups, servings_factor, wanted_servings
from ..models import Recipe, RecipeIngredient, Step, Tag
from ..photos import PhotoError
from .recipes import set_photo

bp = Blueprint("discover", __name__)

SOURCE = "themealdb"
FEATURED_AREA = "Filipino"
MAX_INGREDIENTS = 3  # one TheMealDB call each
DEMO_MAX_SAVED = 10
DOWN_MESSAGE = "We can't reach TheMealDB right now, so recipe ideas are unavailable. Please try again later."


def candidates(s, name):
    """A typed name -> [our name, its aliases...] to try on TheMealDB ("bawang" -> garlic)."""
    ingredient = ingredients.resolve(s, name)
    if ingredient is None:
        return [name]
    return [ingredient.name] + sorted(alias.alias for alias in ingredient.aliases)


def saved_ids(s):
    """{TheMealDB id: our recipe id} for what this user already saved."""
    rows = s.execute(select(Recipe.external_id, Recipe.id)
                     .where(Recipe.user_id == g.user.id, Recipe.source == SOURCE)).all()
    return dict(rows)


@bp.get("/discover")
@login_required
def index():
    s = db.session()
    q = request.args.get("q", "").strip()[:60]
    have_names = search.split_names(request.args.get("have"))[:MAX_INGREDIENTS]
    area = request.args.get("area", "").strip()[:40]
    category = request.args.get("category", "").strip()[:40]
    if not (q or have_names or area or category):
        area = FEATURED_AREA

    meals, error = [], None
    try:
        if have_names:
            meals = mealdb.by_ingredients([candidates(s, name) for name in have_names])
        elif q:
            meals = mealdb.search_name(q)
        elif area:
            meals = mealdb.by_area(area)
        else:
            meals = mealdb.by_category(category)
    except mealdb.MealDBError:
        error = DOWN_MESSAGE
    try:
        areas, categories = mealdb.list_areas(), mealdb.list_categories()
    except mealdb.MealDBError:
        areas, categories = [], []

    # "Already in your recipes?": the same question asked of your own box.
    mine = []
    if have_names or q:
        have_ids = [i.id for i in (ingredients.resolve(s, n) for n in have_names) if i is not None]
        if have_names and len(have_ids) == len(have_names):
            mine = [r.recipe for r in search.run(s, g.user.id, search.Query(have=have_ids, mode="all"))]
        elif q:
            mine = [r.recipe for r in search.run(s, g.user.id, search.Query(text=q))]
    return render_template(
        "discover.html", meals=meals, error=error, q=q, have_text=", ".join(have_names),
        area=area, category=category, areas=areas, categories=categories,
        saved=saved_ids(s), mine=mine[:6], suggestions=ingredients.suggestions(s, g.user.id),
        max_ingredients=MAX_INGREDIENTS, featured=area == FEATURED_AREA and not request.args.get("area"),
    )


def get_meal(meal_id):
    try:
        meal = mealdb.lookup(meal_id)
    except mealdb.MealDBError:
        abort(503, DOWN_MESSAGE)
    if meal is None:
        abort(404)
    return mealdb.to_recipe(meal)


@bp.get("/discover/<meal_id>")
@login_required
def show(meal_id):
    recipe = get_meal(meal_id)
    servings = wanted_servings(request.args.get("servings"), recipe["servings"])
    groups = ingredient_groups(recipe["ingredients"], servings_factor(recipe["servings"], servings))
    return render_template("discover_meal.html", recipe=recipe, groups=groups, servings=servings,
                           saved_id=saved_ids(db.session()).get(recipe["id"]))


@bp.get("/discover/<meal_id>/cook")
@login_required
def cook(meal_id):
    recipe = get_meal(meal_id)
    servings = wanted_servings(request.args.get("servings"), recipe["servings"])
    groups = ingredient_groups(recipe["ingredients"], servings_factor(recipe["servings"], servings))
    return render_template("cook.html", title=recipe["title"], steps=recipe["steps"], groups=groups,
                           servings=servings,
                           back=url_for("discover.show", meal_id=recipe["id"], servings=servings))


@bp.post("/discover/<meal_id>/save")
@login_required
def save(meal_id):
    """Copy a TheMealDB recipe into your own recipes (once)."""
    s = db.session()
    existing = saved_ids(s).get(str(meal_id))
    if existing:
        flash("You've already saved this recipe. Here it is.")
        return redirect(url_for("recipes.show", recipe_id=existing))
    if g.user.is_demo:
        count = s.scalar(select(func.count()).select_from(Recipe)
                         .where(Recipe.user_id == g.user.id, Recipe.source == SOURCE))
        if count >= DEMO_MAX_SAVED:
            abort(403, f"The demo can save up to {DEMO_MAX_SAVED} recipe ideas.")

    data = get_meal(meal_id)
    tags = []
    for name in data["tags"]:
        tag = s.scalar(select(Tag).where(Tag.user_id == g.user.id, Tag.name == name))
        tags.append(tag or Tag(user_id=g.user.id, name=name))
    # "Aubergine" finds our "eggplant" through its alias, so search works on saved recipes too.
    found = [ingredients.get_or_create(s, row["name"]) for row in data["ingredients"]]
    with s.no_autoflush:
        recipe = Recipe(
            user_id=g.user.id, source=SOURCE, external_id=data["id"], title=data["title"],
            description=data["description"], servings=data["servings"], source_url=data["source_url"][:500],
            notes=f"Video: {data['youtube']}" if data["youtube"] else "", tags=tags,
            ingredients=[
                RecipeIngredient(ingredient=ingredient, amount=row["amount"], amount_max=row["amount_max"],
                                 unit=row["unit"], note=row["note"], position=position)
                for position, (row, ingredient) in enumerate(zip(data["ingredients"], found))
            ],
            steps=[Step(text=text, position=position) for position, text in enumerate(data["steps"])],
        )
        s.add(recipe)

    if data["image"]:
        try:
            set_photo(recipe, mealdb.FETCH_BYTES(data["image"] + "/large"))
        except (mealdb.MealDBError, PhotoError, OSError, ValueError):
            pass  # the recipe is still worth saving without its picture
    s.commit()
    flash(f"Saved “{recipe.title}” to your recipes. You can now edit it.")
    return redirect(url_for("recipes.show", recipe_id=recipe.id))


@bp.app_errorhandler(503)
def unavailable(error):
    return render_template("error.html", code=503, message=error.description), 503
