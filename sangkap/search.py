"""Find your recipes by ingredient (and by words, tags, time).

All the search SQL lives here. Four ways to use the ingredients you list:

  all      recipes that have EVERY one of them
           JOIN recipe_ingredients, keep only those ingredients,
           GROUP BY recipe HAVING COUNT(DISTINCT ingredient_id) = how many you listed
  any      recipes with at least ONE of them, the best matches first
           the same GROUP BY, ORDER BY the count
  pantry   "What Can I Cook?": recipes where the needed ingredients you
           DON'T have are few (0, 1, 2...). Optional ones never count as missing,
           and neither do STAPLES (water, salt, oil, pepper).
           COUNT(DISTINCT CASE WHEN ingredient_id NOT IN (yours) THEN ... END) <= N
  (and "without": recipes with none of these, as NOT EXISTS)

Only the user's own recipes are ever searched (WHERE recipes.user_id = ?).
Where it's used: "What Can I Cook?" (views/ingredients.index) picks the
ingredients from your fridge and pantry; My Recipes (views/recipes.index)
searches by name with `text`.
"""
from dataclasses import dataclass, field

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.orm import selectinload

from . import ingredients
from .models import Recipe, RecipeIngredient, Tag

MODES = ("all", "any", "pantry")
MAX_INGREDIENTS = 12
# The "Match" menu on "What can I cook?": value -> (label, mode, missing_max).
MATCHES = {
    "ready": ("Ready to cook (I have everything)", "pantry", 0),
    "missing1": ("Missing 1 ingredient at most", "pantry", 1),
    "missing2": ("Missing 2 ingredients at most", "pantry", 2),
    "all": ("Uses all I picked", "all", 0),
    "any": ("Uses any I picked", "any", 0),
}
DEFAULT_MATCH = "missing1"
# Almost every kitchen has these, so they never count as missing; otherwise
# nearly every recipe would miss 2-3 things (most recipes list water, salt and oil).
STAPLES = ("water", "salt", "cooking oil", "black pepper")


@dataclass
class Result:
    recipe: Recipe
    matched: list = field(default_factory=list)   # names you have that it uses
    missing: list = field(default_factory=list)   # needed names you don't have
    optional: list = field(default_factory=list)  # optional names you don't have


@dataclass
class Query:
    have: list = field(default_factory=list)       # ingredient ids
    without: list = field(default_factory=list)    # ingredient ids
    mode: str = "all"
    missing_max: int = 1                            # for "pantry"
    text: str = ""
    tag_ids: list = field(default_factory=list)
    max_minutes: int | None = None
    favorites: bool = False
    staples: list = field(default_factory=list)    # ingredient ids that are never "missing"

    def is_empty(self):
        return not (self.have or self.without or self.text or self.tag_ids or self.max_minutes or self.favorites)


def split_names(text):
    """ "chicken, Garlic ,, gata" -> ["chicken", "garlic", "gata"] (no repeats)."""
    names = []
    for part in (text or "").split(","):
        name = ingredients.normalize(part)
        if name and name not in names:
            names.append(name)
    return names[:MAX_INGREDIENTS]


def resolve_staples(s):
    """The ingredient ids of STAPLES (they never count as missing)."""
    ids = []
    for name in STAPLES:
        ingredient = ingredients.resolve(s, name)
        if ingredient is not None:
            ids.append(ingredient.id)
    return ids


def like_pattern(text):
    """Words -> a LIKE pattern. % and _ typed by the person are matched as themselves."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def ingredient_counts(have, staples=()):
    """A sub-query: per recipe, how many of `have` it uses, and how many needed ones it misses."""
    line = RecipeIngredient
    in_have = line.ingredient_id.in_(have)
    needed = and_(~in_have, ~line.ingredient_id.in_(list(staples)), line.is_optional.is_(False))
    return (
        select(
            line.recipe_id.label("recipe_id"),
            func.count(distinct(case((in_have, line.ingredient_id)))).label("matched"),
            func.count(distinct(case((needed, line.ingredient_id)))).label("missing"),
        )
        .group_by(line.recipe_id)
        .subquery()
    )


def build(user_id, q):
    """The SELECT for a search (without running it). Tests print it to learn from."""
    query = select(Recipe).where(Recipe.user_id == user_id)

    if q.text:
        pattern = like_pattern(q.text)
        query = query.where(or_(
            Recipe.title.ilike(pattern, escape="\\"),
            Recipe.description.ilike(pattern, escape="\\"),
            Recipe.notes.ilike(pattern, escape="\\"),
        ))
    for tag_id in q.tag_ids:
        # One .any() per tag, so a recipe needs EVERY chosen tag.
        query = query.where(Recipe.tags.any(Tag.id == tag_id))
    if q.max_minutes:
        total = func.coalesce(Recipe.prep_minutes, 0) + func.coalesce(Recipe.cook_minutes, 0)
        query = query.where(total <= q.max_minutes, or_(Recipe.prep_minutes.is_not(None),
                                                         Recipe.cook_minutes.is_not(None)))
    if q.favorites:
        query = query.where(Recipe.is_favorite.is_(True))
    if q.without:
        # NOT EXISTS (SELECT 1 FROM recipe_ingredients WHERE recipe_id = recipes.id AND ingredient_id IN (...))
        query = query.where(~Recipe.ingredients.any(RecipeIngredient.ingredient_id.in_(q.without)))

    if q.have:
        counts = ingredient_counts(q.have, q.staples)
        query = query.join(counts, counts.c.recipe_id == Recipe.id)
        if q.mode == "all":
            query = query.where(counts.c.matched == len(set(q.have))).order_by(Recipe.title)
        elif q.mode == "any":
            query = query.where(counts.c.matched > 0).order_by(counts.c.matched.desc(), Recipe.title)
        else:  # pantry
            query = query.where(counts.c.matched > 0, counts.c.missing <= q.missing_max)
            query = query.order_by(counts.c.missing, counts.c.matched.desc(), Recipe.title)
    else:
        query = query.order_by(Recipe.title)

    # Load each result's lines, tags and photo in 3 more queries in total
    # (not 3 per recipe: that would be the "N+1 queries" problem).
    return query.options(
        selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient),
        selectinload(Recipe.tags),
        selectinload(Recipe.photo),
    )


def run(s, user_id, q):
    """Search, and say for each result which of your ingredients it uses and lacks."""
    have = set(q.have)
    staples = set(q.staples)
    results = []
    for recipe in s.scalars(build(user_id, q)).unique():
        result = Result(recipe)
        seen = set()
        for line in recipe.ingredients:
            if line.ingredient_id in seen:
                continue  # garlic twice (marinade and sauce) counts once
            seen.add(line.ingredient_id)
            name = line.ingredient.name
            if line.ingredient_id in have:
                result.matched.append(name)
            elif line.ingredient_id in staples:
                continue
            elif line.is_optional:
                result.optional.append(name)
            else:
                result.missing.append(name)
        results.append(result)
    return results
