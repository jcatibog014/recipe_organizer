"""The data model: every table, as a Python class.

    users ─┬─< recipes ─┬─< recipe_ingredients >── ingredients ─< ingredient_aliases
           │            ├─< steps
           │            ├── photos (0 or 1)
           │            └─< recipe_tags >── tags
           ├─< tags
           └─< plan_entries >── recipes

The two many-to-many links are the main lesson:

* Recipe <-> Tag is a PLAIN many-to-many. The link table recipe_tags only
  holds the two ids, so it is a Table, and relationship(secondary=...)
  writes and deletes its rows for us: recipe.tags.append(tag).

* Recipe <-> Ingredient is an ASSOCIATION OBJECT. The link has data of its
  own (amount, unit, note, order...), so the link is a class,
  RecipeIngredient: recipe.ingredients -> RecipeIngredient -> .ingredient.

Every row a person makes belongs to a user (user_id). The ingredient
catalog is the exception: it is shared, so "garlic" is one row however
many recipes use it.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Integer, LargeBinary,
    String, Table, Text, UniqueConstraint,
)
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .dates import utcnow
from .db import Base

TITLE_MAX = 120
NAME_MAX = 60  # ingredient names and aliases
TAG_MAX = 30
NOTE_MAX = 120
UNIT_MAX = 20
SECTION_MAX = 60
URL_MAX = 500


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_reset_at: Mapped[datetime | None] = mapped_column(DateTime)
    # 5 wrong passwords lock the login for 15 minutes (auth.py).
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)

    # Deleting a user deletes their recipes and tags too (cascade).
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    plan_entries: Mapped[list["PlanEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# The plain many-to-many link: just two ids, and together they are the key,
# so a recipe can't have the same tag twice. Deleting a recipe or a tag
# deletes its link rows (ON DELETE CASCADE); the other side stays.
recipe_tags = Table(
    "recipe_tags",
    Base.metadata,
    Column("recipe_id", ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        CheckConstraint("servings BETWEEN 1 AND 100", name="servings_range"),
        # Saving the same TheMealDB recipe twice opens the saved copy instead.
        # (Own recipes have external_id NULL, and NULLs never clash in UNIQUE.)
        UniqueConstraint("user_id", "source", "external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    # "own" (typed in here) or "themealdb" (saved from Discover; external_id is its id there).
    source: Mapped[str] = mapped_column(String(20), default="own")
    external_id: Mapped[str | None] = mapped_column(String(40))
    # Set = anyone with the link /r/<share_code> can read this recipe. NULL = private.
    share_code: Mapped[str | None] = mapped_column(String(24), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    servings: Mapped[int] = mapped_column(Integer, default=4)
    prep_minutes: Mapped[int | None] = mapped_column(Integer)
    cook_minutes: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(String(URL_MAX), default="")
    notes: Mapped[str] = mapped_column(Text, default="")  # private: never on a shared page
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="recipes")
    # ordering_list keeps .position = 0, 1, 2... in list order, so moving a
    # row in the Python list is all it takes to reorder it in the database.
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        order_by="RecipeIngredient.position",
        collection_class=ordering_list("position"),
        cascade="all, delete-orphan",
    )
    steps: Mapped[list["Step"]] = relationship(
        back_populates="recipe",
        order_by="Step.position",
        collection_class=ordering_list("position"),
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary=recipe_tags, back_populates="recipes", order_by="Tag.name",
    )
    # uselist=False: a recipe has 0 or 1 photo (photos.recipe_id is UNIQUE).
    photo: Mapped["Photo | None"] = relationship(
        back_populates="recipe", uselist=False, cascade="all, delete-orphan",
    )

    @property
    def total_minutes(self):
        if self.prep_minutes is None and self.cook_minutes is None:
            return None
        return (self.prep_minutes or 0) + (self.cook_minutes or 0)


class Ingredient(Base):
    """One row per ingredient in the shared catalog ("garlic", "fish sauce")."""
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Always normalized (lower-case, single spaces): see ingredients.normalize().
    name: Mapped[str] = mapped_column(String(NAME_MAX), unique=True)
    # produce / meat / seafood / dairy / pantry / spice / other (for the shopping list)
    kind: Mapped[str] = mapped_column(String(20), default="other")
    # Starter ingredients (ingredients.CATALOG) are never deleted by a cleanup.
    is_seeded: Mapped[bool] = mapped_column(Boolean, default=False)

    aliases: Mapped[list["IngredientAlias"]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan",
    )
    # No cascade here: an ingredient that a recipe uses can't be deleted
    # (ON DELETE RESTRICT on recipe_ingredients.ingredient_id). It can be merged.
    uses: Mapped[list["RecipeIngredient"]] = relationship(back_populates="ingredient")


class IngredientAlias(Base):
    """Another name for an ingredient: "bawang" and "garlic cloves" -> garlic."""
    __tablename__ = "ingredient_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(NAME_MAX), unique=True)

    ingredient: Mapped[Ingredient] = relationship(back_populates="aliases")


class RecipeIngredient(Base):
    """The association object: one ingredient line of one recipe.

    "1 ½ cups coconut milk (gata), optional" is amount=1.5, unit="cup",
    ingredient=<coconut milk>, note="gata", is_optional=True.

    The same ingredient may be in a recipe twice (garlic in the marinade
    AND in the sauce), so there is no UNIQUE (recipe_id, ingredient_id).
    Search counts it once with COUNT(DISTINCT ingredient_id).
    """
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Numbers, not text, so they can be scaled and added up. None = "to taste".
    amount: Mapped[float | None] = mapped_column(Float)
    amount_max: Mapped[float | None] = mapped_column(Float)  # "2-3 cloves": amount=2, amount_max=3
    unit: Mapped[str] = mapped_column(String(UNIT_MAX), default="")  # one of quantities.UNITS, or ""
    note: Mapped[str] = mapped_column(String(NOTE_MAX), default="")
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    section: Mapped[str] = mapped_column(String(SECTION_MAX), default="")  # "For the sauce"

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient] = relationship(back_populates="uses")


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)

    recipe: Mapped[Recipe] = relationship(back_populates="steps")


class Tag(Base):
    """A user's own label for recipes: "soup", "quick", "for guests"."""
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(TAG_MAX))  # lower-case

    user: Mapped[User] = relationship(back_populates="tags")
    recipes: Mapped[list[Recipe]] = relationship(secondary=recipe_tags, back_populates="tags")


class Photo(Base):
    """A recipe's photo, resized and stored in the database.

    Render's free disk forgets files on every restart, so the bytes live
    here (about 50-120 KB each). It is its own table, and `data` is
    deferred: listing recipes never loads the image bytes by accident.
    """
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), unique=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    mime: Mapped[str] = mapped_column(String(20))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size: Mapped[int] = mapped_column(Integer)

    recipe: Mapped[Recipe] = relationship(back_populates="photo")


class PlanEntry(Base):
    """One recipe on the meal plan: "Tuesday dinner: adobo for 6"."""
    __tablename__ = "plan_entries"
    __table_args__ = (
        CheckConstraint("meal IN ('breakfast', 'lunch', 'dinner', 'snack')", name="meal_kind"),
        CheckConstraint("servings BETWEEN 1 AND 100", name="servings_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Deleting a recipe takes it off the plan too.
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    meal: Mapped[str] = mapped_column(String(10))
    servings: Mapped[int] = mapped_column(Integer)

    user: Mapped[User] = relationship(back_populates="plan_entries")
    recipe: Mapped[Recipe] = relationship()
