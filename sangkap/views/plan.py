"""The meal plan (a week of recipes) and its shopping list."""
from datetime import timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import db, shopping
from ..auth import login_required
from ..dates import parse_day, today, week_start
from ..models import PlanEntry, Recipe, RecipeIngredient
from ..validation import whole_number
from . import owned_recipe

bp = Blueprint("plan", __name__)

MEALS = ("breakfast", "lunch", "dinner", "snack")
MEAL_LABELS = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snack": "Snack"}
DEMO_MAX_ENTRIES = 60


def chosen_week():
    """The Monday of ?week=YYYY-MM-DD (any day of that week), or of this week."""
    return week_start(parse_day(request.values.get("week")) or today())


def week_label(monday):
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday:%b} {monday.day}–{sunday.day}, {sunday.year}"
    return f"{monday:%b} {monday.day} – {sunday:%b} {sunday.day}, {sunday.year}"


def week_entries(monday, with_ingredients=False):
    options = [selectinload(PlanEntry.recipe)]
    if with_ingredients:
        options = [selectinload(PlanEntry.recipe).selectinload(Recipe.ingredients)
                   .selectinload(RecipeIngredient.ingredient)]
    return db.session().scalars(
        select(PlanEntry)
        .where(PlanEntry.user_id == g.user.id, PlanEntry.day >= monday,
               PlanEntry.day < monday + timedelta(days=7))
        .options(*options)
        .order_by(PlanEntry.day, PlanEntry.id)
    ).all()


@bp.get("/plan")
@login_required
def index():
    monday = chosen_week()
    entries = week_entries(monday)
    days = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        meals = [(meal, [e for e in entries if e.day == day and e.meal == meal]) for meal in MEALS]
        days.append((day, meals))
    recipes = db.session().scalars(
        select(Recipe).where(Recipe.user_id == g.user.id).order_by(Recipe.title)
    ).all()
    try:
        add_id = int(request.args.get("add", ""))
    except ValueError:
        add_id = None
    return render_template(
        "plan.html", days=days, monday=monday, label=week_label(monday), today=today(),
        recipes=recipes, add_id=add_id, meal_kinds=MEALS, meal_labels=MEAL_LABELS,
        this_week=week_start(today()),
        previous=monday - timedelta(days=7), next=monday + timedelta(days=7), count=len(entries),
    )


@bp.post("/plan/add")
@login_required
def add():
    monday = chosen_week()
    day = parse_day(request.form.get("day"))
    meal = request.form.get("meal")
    try:
        recipe = owned_recipe(int(request.form.get("recipe_id", "")))
    except ValueError:
        abort(400, "Choose a recipe.")
    try:
        servings = whole_number(request.form.get("servings"), 1, 100) or recipe.servings
    except ValueError:
        servings = recipe.servings
    if day is None or meal not in MEALS:
        abort(400, "Choose a day and a meal.")
    s = db.session()
    if g.user.is_demo and len(g.user.plan_entries) >= DEMO_MAX_ENTRIES:
        abort(403, f"The demo can plan up to {DEMO_MAX_ENTRIES} meals.")
    s.add(PlanEntry(user_id=g.user.id, recipe=recipe, day=day, meal=meal, servings=servings))
    s.commit()
    flash(f"Added {recipe.title} to {day:%A}.")
    return redirect(url_for("plan.index", week=monday.isoformat()) + f"#day-{day.isoformat()}")


@bp.post("/plan/<int:entry_id>/delete")
@login_required
def delete(entry_id):
    s = db.session()
    entry = s.get(PlanEntry, entry_id)
    if entry is None or entry.user_id != g.user.id:
        abort(404)
    day = entry.day
    s.delete(entry)
    s.commit()
    return redirect(url_for("plan.index", week=week_start(day).isoformat()) + f"#day-{day.isoformat()}")


@bp.get("/plan/shopping")
@login_required
def shopping_list():
    monday = chosen_week()
    entries = week_entries(monday, with_ingredients=True)
    return render_template("shopping.html", groups=shopping.build(entries), entries=entries,
                           monday=monday, label=week_label(monday))
