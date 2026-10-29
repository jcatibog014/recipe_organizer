"""The shared ingredient catalog: clean names, aliases, merging.

Every ingredient line points at one catalog row, so "garlic" is one row
however many recipes use it. That is what makes "search by ingredient"
possible: it is a JOIN on ingredient_id, not a text search.

Names are always normalized first ("  Garlic  CLOVES " -> "garlic cloves"),
and aliases map other names to the same row ("bawang" -> garlic), so
Filipino and English names find the same recipes.
"""
import re

from sqlalchemy import distinct, exists, func, or_, select

from .models import NAME_MAX, Ingredient, IngredientAlias, Recipe, RecipeIngredient

KINDS = ("produce", "meat", "seafood", "dairy", "pantry", "spice", "other")
KIND_LABELS = {
    "produce": "Fruits & vegetables",
    "meat": "Meat",
    "seafood": "Fish & seafood",
    "dairy": "Eggs & dairy",
    "pantry": "Pantry",
    "spice": "Herbs & spices",
    "other": "Other",
}

# The starter catalog: (name, kind, aliases).
# add_catalog() puts these into every database (flask upgrade-db, and the tests).
CATALOG = [
    # Fruits & vegetables
    ("garlic", "produce", ["bawang", "garlic clove", "garlic cloves", "cloves garlic"]),
    ("onion", "produce", ["sibuyas", "onions", "red onion", "white onion", "yellow onion"]),
    ("tomato", "produce", ["kamatis", "tomatoes"]),
    ("ginger", "produce", ["luya", "ginger root"]),
    ("chili", "produce", ["sili", "siling labuyo", "chilies", "chillies", "chili pepper",
                               "red chili", "bird's eye chili", "chilli"]),
    ("long green chili", "produce", ["siling haba", "siling pansigang", "finger chili",
                                          "green chili", "green chilies"]),
    ("calamansi", "produce", ["kalamansi", "calamondin", "calamansi juice"]),
    ("lemon", "produce", ["lemons", "lemon juice"]),
    ("lime", "produce", ["limes", "lime juice"]),
    ("carrot", "produce", ["karot", "carrots"]),
    ("potato", "produce", ["patatas", "potatoes"]),
    ("sweet potato", "produce", ["kamote", "sweet potatoes"]),
    ("eggplant", "produce", ["talong", "eggplants", "aubergine"]),
    ("squash", "produce", ["kalabasa", "pumpkin"]),
    ("string beans", "produce", ["sitaw", "long beans", "yardlong beans"]),
    ("green beans", "produce", ["baguio beans"]),
    ("okra", "produce", []),
    ("bitter gourd", "produce", ["ampalaya", "bitter melon"]),
    ("cabbage", "produce", ["repolyo"]),
    ("pechay", "produce", ["bok choy", "pak choi", "petsay"]),
    ("kangkong", "produce", ["water spinach"]),
    ("spinach", "produce", ["kulitis"]),
    ("malunggay", "produce", ["moringa", "moringa leaves", "malunggay leaves"]),
    ("chayote", "produce", ["sayote"]),
    ("radish", "produce", ["labanos", "daikon"]),
    ("bell pepper", "produce", ["capsicum", "red bell pepper", "green bell pepper", "bell peppers"]),
    ("green onion", "produce", ["spring onion", "spring onions", "scallion", "scallions",
                                     "dahon ng sibuyas"]),
    ("lemongrass", "produce", ["tanglad"]),
    ("mushroom", "produce", ["mushrooms", "kabute"]),
    ("banana", "produce", ["saging", "saba", "saba banana", "saba bananas", "bananas"]),
    ("mango", "produce", ["mangga", "mangoes", "ripe mango", "ripe mangoes"]),
    ("jackfruit", "produce", ["langka"]),
    ("coconut", "produce", ["niyog", "grated coconut"]),
    ("tamarind", "produce", ["sampalok"]),
    ("corn", "produce", ["mais", "sweet corn"]),
    ("cucumber", "produce", ["pipino"]),
    ("lettuce", "produce", []),
    ("celery", "produce", ["kintsay"]),
    ("peas", "produce", ["green peas", "gisantes"]),
    ("bean sprouts", "produce", ["toge", "mung bean sprouts"]),
    ("taro", "produce", ["gabi"]),
    ("ube", "produce", ["purple yam", "ube halaya"]),
    # Meat
    ("chicken", "meat", ["manok", "chicken thighs", "chicken breast", "chicken legs",
                              "chicken drumsticks", "chicken pieces", "chicken wings"]),
    ("chicken liver", "meat", ["atay ng manok"]),
    ("pork", "meat", ["baboy", "pork shoulder", "kasim", "pork cubes", "pork ribs"]),
    ("pork belly", "meat", ["liempo"]),
    ("ground pork", "meat", ["giniling", "minced pork"]),
    ("pork hock", "meat", ["pata"]),
    ("pork liver", "meat", ["atay"]),
    ("beef", "meat", ["baka", "beef chunks", "beef sirloin", "stewing beef"]),
    ("ground beef", "meat", ["minced beef"]),
    ("oxtail", "meat", ["buntot ng baka"]),
    ("chorizo", "meat", ["chorizo de bilbao"]),
    ("hotdog", "meat", ["hot dog", "hotdogs"]),
    ("bacon", "meat", []),
    # Fish & seafood
    ("fish", "seafood", ["isda", "fish fillet"]),
    ("milkfish", "seafood", ["bangus"]),
    ("tilapia", "seafood", []),
    ("shrimp", "seafood", ["hipon", "prawns", "prawn", "shrimps"]),
    ("squid", "seafood", ["pusit", "calamari"]),
    ("crab", "seafood", ["alimango", "alimasag"]),
    ("mussels", "seafood", ["tahong"]),
    ("clams", "seafood", ["halaan", "tulya"]),
    ("dried fish", "seafood", ["tuyo", "daing"]),
    ("tuna", "seafood", ["canned tuna"]),
    # Eggs & dairy
    ("egg", "dairy", ["eggs", "itlog", "egg yolk", "egg yolks"]),
    ("milk", "dairy", ["gatas", "fresh milk"]),
    ("evaporated milk", "dairy", ["evap"]),
    ("condensed milk", "dairy", ["sweetened condensed milk"]),
    ("butter", "dairy", ["mantikilya"]),
    ("cheese", "dairy", ["keso", "cheddar cheese"]),
    ("all-purpose cream", "dairy", ["cream", "heavy cream"]),
    # Pantry
    ("rice", "pantry", ["kanin", "bigas", "white rice", "cooked rice", "jasmine rice"]),
    ("glutinous rice", "pantry", ["malagkit", "sticky rice"]),
    ("rice noodles", "pantry", ["bihon", "rice vermicelli", "bihon noodles"]),
    ("canton noodles", "pantry", ["pancit canton", "egg noodles"]),
    ("spaghetti", "pantry", ["pasta"]),
    ("flour", "pantry", ["all-purpose flour", "harina", "plain flour"]),
    ("cornstarch", "pantry", ["cornflour", "corn starch"]),
    ("bread crumbs", "pantry", ["breadcrumbs"]),
    ("bread", "pantry", ["tinapay", "pandesal"]),
    ("soy sauce", "pantry", ["toyo"]),
    ("vinegar", "pantry", ["suka", "cane vinegar", "white vinegar"]),
    ("fish sauce", "pantry", ["patis"]),
    ("oyster sauce", "pantry", []),
    ("shrimp paste", "pantry", ["bagoong", "bagoong alamang"]),
    ("coconut milk", "pantry", ["gata", "coconut cream", "kakang gata"]),
    ("cooking oil", "pantry", ["oil", "vegetable oil", "mantika"]),
    ("olive oil", "pantry", []),
    ("sugar", "pantry", ["asukal", "white sugar", "granulated sugar"]),
    ("brown sugar", "pantry", ["muscovado"]),
    ("salt", "spice", ["asin", "sea salt"]),
    ("peanut butter", "pantry", []),
    ("peanuts", "pantry", ["mani", "roasted peanuts"]),
    ("tomato sauce", "pantry", []),
    ("tomato paste", "pantry", []),
    ("banana ketchup", "pantry", ["ketchup"]),
    ("liver spread", "pantry", ["reno"]),
    ("sinigang mix", "pantry", ["tamarind soup mix", "sinigang sa sampalok mix"]),
    ("chicken broth", "pantry", ["chicken stock", "broth", "stock"]),
    ("water", "pantry", ["tubig"]),
    ("mung beans", "pantry", ["monggo", "munggo"]),
    ("cocoa", "pantry", ["tablea", "cocoa powder", "chocolate"]),
    ("spring roll wrappers", "pantry", ["lumpia wrapper", "lumpia wrappers"]),
    ("graham crackers", "pantry", []),
    ("sago pearls", "pantry", ["sago", "tapioca pearls"]),
    ("red beans", "pantry", ["sweetened red beans"]),
    ("tofu", "pantry", ["tokwa"]),
    ("ice", "other", ["shaved ice", "crushed ice"]),
    # Herbs & spices
    ("black pepper", "spice", ["pepper", "paminta", "ground black pepper", "peppercorns",
                                    "whole peppercorns"]),
    ("bay leaf", "spice", ["bay leaves", "dahon ng laurel", "laurel"]),
    ("annatto", "spice", ["atsuete", "achuete", "annatto seeds"]),
    ("paprika", "spice", []),
    ("chili flakes", "spice", ["red pepper flakes"]),
    ("vanilla", "spice", ["vanilla extract"]),
]

def normalize(name):
    """The catalog form of a name: lower-case, single spaces, no bullet marks.

    "  Garlic  CLOVES. " -> "garlic cloves"
    """
    name = re.sub(r"\s+", " ", (name or "").strip().lower())
    name = name.strip(" .,;:-*•·")
    return name[:NAME_MAX]


def resolve(s, name):
    """The catalog row for a name or alias, or None. Doesn't add anything."""
    name = normalize(name)
    if not name:
        return None
    ingredient = s.scalar(select(Ingredient).where(Ingredient.name == name))
    if ingredient is None:
        ingredient = s.scalar(
            select(Ingredient).join(IngredientAlias).where(IngredientAlias.alias == name)
        )
    if ingredient is None and len(name) > 3:
        # A simple plural: "carrots" -> "carrot", "tomatoes" -> "tomato".
        for ending in ("es", "s"):
            if name.endswith(ending):
                singular = name[: -len(ending)]
                ingredient = s.scalar(select(Ingredient).where(Ingredient.name == singular))
                if ingredient:
                    break
    return ingredient


def get_or_create(s, name, kind="other"):
    """The catalog row for this name, added if it's new. The caller commits."""
    ingredient = resolve(s, name)
    if ingredient is None:
        ingredient = Ingredient(name=normalize(name), kind=kind)
        s.add(ingredient)
        s.flush()  # gives it an id now
    return ingredient


def add_catalog(s):
    """Add the CATALOG rows that aren't there yet. Returns how many were new.

    Safe to run again and again: it only adds what's missing.
    """
    names = set(s.scalars(select(Ingredient.name)))
    aliases = set(s.scalars(select(IngredientAlias.alias)))
    added = 0
    for name, kind, alias_list in CATALOG:
        if name in names:
            ingredient = s.scalar(select(Ingredient).where(Ingredient.name == name))
        else:
            ingredient = Ingredient(name=name, kind=kind, is_seeded=True)
            s.add(ingredient)
            names.add(name)
            added += 1
        for alias in alias_list:
            if alias not in aliases and alias not in names:
                ingredient.aliases.append(IngredientAlias(alias=alias))
                aliases.add(alias)
    s.flush()
    return added


def used_by(user_id):
    """SQL condition: this user has a recipe that uses the ingredient."""
    return exists().where(
        RecipeIngredient.ingredient_id == Ingredient.id,
        RecipeIngredient.recipe_id == Recipe.id,
        Recipe.user_id == user_id,
    )


def suggestions(s, user_id):
    """Names for the autocomplete list: the starter catalog + your own.

    Other users' new ingredients are never shown, so the demo's typing
    can't show up in the owner's forms.
    """
    return list(s.scalars(
        select(Ingredient.name)
        .where(or_(Ingredient.is_seeded.is_(True), used_by(user_id)))
        .order_by(Ingredient.name)
    ))


def usage(s, user_id):
    """[(ingredient, how many of your recipes use it)], most used first.

    SELECT ingredients.*, COUNT(DISTINCT recipe_ingredients.recipe_id)
    FROM ingredients JOIN recipe_ingredients ... JOIN recipes ...
    WHERE recipes.user_id = ? GROUP BY ingredients.id
    """
    count = func.count(distinct(RecipeIngredient.recipe_id))
    return s.execute(
        select(Ingredient, count)
        .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
        .where(Recipe.user_id == user_id)
        .group_by(Ingredient.id)
        .order_by(count.desc(), Ingredient.name)
    ).all()


def merge(s, user_id, source, target_name, keep_alias=True):
    """Move this user's uses of `source` to `target_name` (made if new).

    That's both "rename" and "merge onions into onion". The catalog is
    shared, so only YOUR recipe lines move. When nobody uses `source`
    any more, it is deleted, and (keep_alias) its name becomes an alias
    of the target, so typing the old name still finds the recipes.
    Returns (target, how many lines moved). The caller commits.
    """
    target = get_or_create(s, target_name)
    if target.id == source.id:
        return target, 0
    lines = s.scalars(
        select(RecipeIngredient).join(Recipe)
        .where(RecipeIngredient.ingredient_id == source.id, Recipe.user_id == user_id)
    ).all()
    for line in lines:
        line.ingredient = target
    s.flush()

    still_used = s.scalar(select(exists().where(RecipeIngredient.ingredient_id == source.id)))
    if not still_used and not source.is_seeded:
        if keep_alias:
            for alias in list(source.aliases):
                alias.ingredient = target
            taken = s.scalar(select(IngredientAlias).where(IngredientAlias.alias == source.name))
            if taken is None:
                target.aliases.append(IngredientAlias(alias=source.name))
        s.delete(source)
        s.flush()
    return target, len(lines)


def delete_unused(s):
    """Delete non-starter ingredients that no recipe uses (after a demo reset)."""
    unused = s.scalars(
        select(Ingredient).where(
            Ingredient.is_seeded.is_(False),
            ~exists().where(RecipeIngredient.ingredient_id == Ingredient.id),
        )
    ).all()
    for ingredient in unused:
        s.delete(ingredient)
    return len(unused)
