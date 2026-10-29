"""The shopping list: add up the ingredients of the week's planned recipes.

Each planned recipe is scaled to its planned servings (adobo for 4 planned
for 8 = double). Lines for the same ingredient are added up:

    2 tbsp + 1 tbsp          -> 3 tbsp
    1 cup + 2 tbsp           -> 1 ⅛ cups     (same family: turned into the bigger unit)
    500 g + 1 kg             -> 1 ½ kg
    2 pcs + 1 cup            -> 2 pcs + 1 cup (can't be added: shown side by side)
    "salt, to taste" (no amount) -> listed with no amount

Totals round UP to the next ⅛ (2.19 cups -> 2 ¼ cups). Optional
ingredients and water are left out. Plain Python (tests/test_plan_and_shopping.py).
"""
import math
from dataclasses import dataclass, field

from .ingredients import KINDS
from .quantities import CONVERSIONS, format_quantity

NOT_BOUGHT = {"water"}  # from the tap: never on the list


@dataclass
class Item:
    name: str
    kind: str
    amounts: dict = field(default_factory=dict)  # unit -> total, before combining
    loose: bool = False  # some recipe needs it with no amount ("to taste")
    recipes: list = field(default_factory=list)

    def add(self, amount, unit):
        self.amounts[unit] = self.amounts.get(unit, 0) + amount

    def totals(self):
        """[(amount, unit)], with units of one family combined into the biggest one used."""
        families = {}
        others = []
        for unit, amount in self.amounts.items():
            if unit in CONVERSIONS:
                family, _size = CONVERSIONS[unit]
                families.setdefault(family, []).append((unit, amount))
            else:
                others.append((amount, unit))
        combined = []
        for units in families.values():
            biggest = max((unit for unit, _ in units), key=lambda unit: CONVERSIONS[unit][1])
            size = CONVERSIONS[biggest][1]
            total = sum(amount * CONVERSIONS[unit][1] for unit, amount in units) / size
            combined.append((total, biggest))
        return combined + sorted(others, key=lambda pair: pair[1])

    def quantities(self):
        return [format_quantity(round_up(amount), None, unit) for amount, unit in self.totals()]


def round_up(amount):
    """Up to the next ⅛, so you buy enough: 2.19 cups -> 2 ¼ cups (never "2.19").

    Thirds are kept as they are (⅓ cup stays ⅓, not ⅜).
    """
    if abs(amount * 3 - round(amount * 3)) < 0.01:
        return amount
    return math.ceil(amount * 8 - 1e-9) / 8


def build(entries):
    """Plan entries (with .recipe loaded) -> [(kind, [Item, ...]), ...] in shelf order."""
    items = {}
    for entry in entries:
        recipe = entry.recipe
        factor = entry.servings / recipe.servings if recipe.servings else 1
        for line in recipe.ingredients:
            if line.is_optional or line.ingredient.name in NOT_BOUGHT:
                continue
            ingredient = line.ingredient
            item = items.get(ingredient.id)
            if item is None:
                item = items[ingredient.id] = Item(name=ingredient.name, kind=ingredient.kind)
            if recipe.title not in item.recipes:
                item.recipes.append(recipe.title)
            if line.amount is None:
                item.loose = True
            else:
                # For a range ("2-3 cloves") buy the bigger number.
                amount = line.amount_max if line.amount_max is not None else line.amount
                item.add(amount * factor, line.unit)

    by_kind = {}
    for item in items.values():
        by_kind.setdefault(item.kind if item.kind in KINDS else "other", []).append(item)
    return [(kind, sorted(by_kind[kind], key=lambda item: item.name)) for kind in KINDS if kind in by_kind]
