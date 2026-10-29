"""Sample data for the demo account: 9 Filipino recipes and a meal plan.

There are only a few on purpose, so the demo (and the README screenshots)
stay short and easy to look through.

The ingredient lists are written the way people paste them, and
paste.parse_block() turns them into rows: the same code the form uses.
"""
from datetime import timedelta

from sqlalchemy import delete

from . import ingredients, paste
from .dates import today, week_start
from .models import PlanEntry, Recipe, RecipeIngredient, Step, Tag

DEMO_RECIPES = [
    {
        "title": "Chicken Adobo", "tags": "chicken, ulam, classic", "servings": 4, "prep": 10, "cook": 45,
        "favorite": True,
        "description": "Salty, sour and garlicky. Even better the next day.",
        "ingredients": """1 kg chicken thighs
1/2 cup soy sauce
1/3 cup vinegar
1 head garlic, crushed
3 pcs bay leaves
1 tsp whole peppercorns
1 tbsp brown sugar (optional)
1 cup water""",
        "steps": [
            "Mix the chicken, soy sauce and garlic. Leave it for 30 minutes if you have time.",
            "Put everything in a pot with the bay leaves, peppercorns and water. Bring to a boil.",
            "Add the vinegar. Don't stir for 2 minutes so the sour taste cooks off.",
            "Simmer for 30-35 minutes until the chicken is soft and the sauce is thick.",
            "Taste, add the sugar if you like it sweeter, and serve with rice.",
        ],
    },
    {
        "title": "Sinigang na Baboy", "tags": "soup, pork, classic", "servings": 6, "prep": 15, "cook": 75,
        "favorite": True,
        "description": "The sour tamarind soup that warms every rainy day.",
        "ingredients": """1 kg pork ribs
2 pcs tomatoes, quartered
1 pc onion, quartered
1 pack sinigang mix
1 pc radish, sliced
1 bunch string beans, cut
1 bunch kangkong
2 pcs long green chili
2 tbsp fish sauce
8 cups water""",
        "steps": [
            "Boil the pork in the water. Skim off the scum, then add the onion and tomatoes.",
            "Simmer for 1 hour until the pork is tender.",
            "Add the sinigang mix and radish. Cook for 5 minutes.",
            "Add the string beans and long green chili. Cook for 3 minutes.",
            "Season with fish sauce, turn off the heat, then add the kangkong.",
        ],
    },
    {
        "title": "Tinolang Manok", "tags": "soup, chicken, comfort", "servings": 5, "prep": 10, "cook": 40,
        "description": "Gentle ginger chicken soup with green papaya or sayote.",
        "ingredients": """1 kg chicken pieces
1 thumb ginger, sliced
4 cloves garlic, crushed
1 pc onion, sliced
2 pcs chayote, cut
1 cup malunggay leaves
2 tbsp fish sauce
6 cups water
1 tbsp cooking oil""",
        "steps": [
            "Sauté the garlic, onion and ginger in the oil.",
            "Add the chicken and fish sauce. Cook until the chicken turns white.",
            "Pour in the water and simmer for 25 minutes.",
            "Add the chayote and cook until soft.",
            "Add the malunggay leaves, turn off the heat and serve.",
        ],
    },
    {
        "title": "Pancit Bihon", "tags": "noodles, party, merienda", "servings": 6, "prep": 20, "cook": 25,
        "description": "Long noodles for a long life. A must at birthdays.",
        "ingredients": """500 g rice noodles
250 g chicken breast, sliced
100 g shrimp (optional)
1 pc carrot, cut into strips
2 cups cabbage, sliced
1 cup green beans, sliced
1 pc onion, sliced
4 cloves garlic, minced
1/4 cup soy sauce
3 cups chicken broth
2 tbsp cooking oil
2 pcs calamansi""",
        "steps": [
            "Soak the noodles in water for 10 minutes, then drain.",
            "Sauté the garlic and onion. Add the chicken (and shrimp) and cook through.",
            "Add the carrot, green beans and cabbage. Cook for 2 minutes, then take half out for later.",
            "Pour in the broth and soy sauce. Bring to a boil.",
            "Add the noodles and toss until the liquid is gone. Top with the vegetables you kept.",
            "Serve with calamansi.",
        ],
    },
    {
        "title": "Champorado", "tags": "breakfast, sweets", "servings": 4, "prep": 5, "cook": 25,
        "description": "Chocolate rice porridge. Try it with tuyo!",
        "ingredients": """1 cup glutinous rice
4 pcs tablea
5 cups water
1/2 cup sugar
1/2 cup evaporated milk""",
        "steps": [
            "Boil the water and melt the tablea in it.",
            "Add the rice and cook for 20 minutes, stirring so it doesn't stick.",
            "Stir in the sugar.",
            "Serve with a swirl of evaporated milk on top.",
        ],
    },
    {
        "title": "Leche Flan", "tags": "dessert, party", "servings": 8, "prep": 20, "cook": 60,
        "favorite": True,
        "description": "Silky caramel custard, the star of every handaan.",
        "ingredients": """10 pcs egg yolks
1 can condensed milk
1 can evaporated milk
1 tsp vanilla extract
For the caramel:
1 cup sugar
1/4 cup water""",
        "steps": [
            "Melt the sugar with the water in the llanera (flan mold) until golden. Let it set.",
            "Gently mix the egg yolks, both milks and vanilla. Don't whisk in air.",
            "Strain the mix into the mold and cover with foil.",
            "Steam over low heat for 45-60 minutes, until set.",
            "Cool, then chill. Run a knife around it and flip it onto a plate.",
        ],
    },
    {
        "title": "Turon", "tags": "merienda, dessert, fried", "servings": 6, "prep": 15, "cook": 15,
        "description": "Banana and jackfruit spring rolls with a crunchy caramel coat.",
        "ingredients": """6 pcs saba bananas, cut in half lengthwise
1/2 cup jackfruit, cut into strips
12 pcs spring roll wrappers
1 cup brown sugar
2 cups cooking oil""",
        "steps": [
            "Roll each banana piece in brown sugar.",
            "Wrap it with a strip of jackfruit in a spring roll wrapper. Seal with water.",
            "Fry in hot oil. Sprinkle in more brown sugar so it caramelizes on the rolls.",
            "Take them out when golden and glossy.",
        ],
    },
    {
        "title": "Sinangag (Garlic Fried Rice)", "tags": "rice, breakfast, quick", "servings": 4, "prep": 5,
        "cook": 10,
        "description": "Yesterday's rice, made the best part of breakfast.",
        "ingredients": """4 cups cooked rice, a day old
8 cloves garlic, minced
1 tsp salt
3 tbsp cooking oil""",
        "steps": [
            "Fry the garlic in the oil over low heat until light brown.",
            "Add the rice and break up the lumps.",
            "Season with salt and stir-fry for 5 minutes.",
        ],
    },
    {
        "title": "Ginisang Monggo", "tags": "vegetables, ulam, comfort", "servings": 6, "prep": 10, "cook": 50,
        "description": "Mung bean stew, a Friday favorite.",
        "ingredients": """1 cup mung beans
6 cups water
200 g pork belly, cubed
1 pc onion, chopped
4 cloves garlic, minced
2 pcs tomatoes, chopped
1 cup malunggay leaves
2 tbsp fish sauce""",
        "steps": [
            "Boil the mung beans in the water for 30 minutes until soft.",
            "In another pan, fry the pork until brown. Add the garlic, onion and tomatoes.",
            "Add the cooked beans with their water. Simmer for 10 minutes.",
            "Season with fish sauce and stir in the malunggay.",
        ],
    },
]

# The demo's week: (day of the week, meal, recipe title). 0 = Monday.
DEMO_PLAN = [
    (0, "dinner", "Chicken Adobo"),
    (1, "lunch", "Sinigang na Baboy"),
    (2, "dinner", "Pancit Bihon"),
    (3, "breakfast", "Champorado"),
    (4, "dinner", "Ginisang Monggo"),
    (5, "snack", "Turon"),
    (6, "lunch", "Tinolang Manok"),
]


def add_recipe(s, user, sample):
    """One DEMO_RECIPES entry -> a Recipe with its lines, steps and tags."""
    tags = []
    for name in [part.strip() for part in sample["tags"].split(",") if part.strip()]:
        tag = next((t for t in user.tags if t.name == name), None)
        if tag is None:
            tag = Tag(name=name)
            user.tags.append(tag)
        tags.append(tag)

    rows = []
    section = ""
    for row in paste.parse_block(sample["ingredients"]):
        if row["kind"] == "section":
            section = row["section"]
        else:
            # Find (or add) the catalog row first; get_or_create may flush the session.
            rows.append((row, section, ingredients.get_or_create(s, row["name"])))

    # Build the recipe and its links, then add it all at once.
    with s.no_autoflush:
        recipe = Recipe(
            title=sample["title"], description=sample["description"], servings=sample["servings"],
            prep_minutes=sample["prep"], cook_minutes=sample["cook"] or None,
            is_favorite=sample.get("favorite", False), tags=tags,
            ingredients=[
                RecipeIngredient(ingredient=ingredient, amount=row["amount"], amount_max=row["amount_max"],
                                 unit=row["unit"], note=row["note"], is_optional=row["is_optional"],
                                 section=section, position=position)
                for position, (row, section, ingredient) in enumerate(rows)
            ],
            steps=[Step(text=text, position=i) for i, text in enumerate(sample["steps"])],
        )
        user.recipes.append(recipe)
    return recipe


def reset_demo(s, user, day=None):
    """Throw away the demo's recipes, tags and plan, and make the samples again."""
    s.execute(delete(PlanEntry).where(PlanEntry.user_id == user.id))
    s.execute(delete(Recipe).where(Recipe.user_id == user.id))
    s.execute(delete(Tag).where(Tag.user_id == user.id))
    s.flush()
    s.expire_all()
    ingredients.delete_unused(s)

    by_title = {sample["title"]: add_recipe(s, user, sample) for sample in DEMO_RECIPES}
    monday = week_start(day or today())
    for weekday, meal, title in DEMO_PLAN:
        recipe = by_title[title]
        user.plan_entries.append(PlanEntry(recipe=recipe, day=monday + timedelta(days=weekday),
                                           meal=meal, servings=recipe.servings))
    s.flush()
