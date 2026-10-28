"""The data model's rules: both many-to-many patterns, cascades and RESTRICT."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from sangkap.ingredients import resolve
from sangkap.models import Ingredient, Photo, Recipe, RecipeIngredient, Step, Tag, recipe_tags

from conftest import add_recipe


def count(s, what):
    return s.scalar(select(func.count()).select_from(what))


def test_plain_many_to_many_writes_the_link_rows(app, owner_id, ctx):
    recipe_id = add_recipe(app, owner_id, "Adobo", tags=["ulam"])
    recipe = ctx.get(Recipe, recipe_id)
    quick = Tag(user_id=owner_id, name="quick")
    recipe.tags.append(quick)           # no link object: SQLAlchemy adds the recipe_tags row
    ctx.commit()
    assert count(ctx, recipe_tags) == 2
    assert quick.recipes == [recipe]    # back_populates: the other side knows too

    recipe.tags.remove(quick)
    ctx.commit()
    assert count(ctx, recipe_tags) == 1
    assert ctx.get(Tag, quick.id) is not None  # removing the link keeps the tag


def test_association_object_carries_its_own_data(app, owner_id, ctx):
    recipe = ctx.get(Recipe, add_recipe(app, owner_id, "Rice", ["1 ½ cups rice, washed"]))
    line = recipe.ingredients[0]
    assert (line.amount, line.unit, line.note, line.ingredient.name) == (1.5, "cup", "washed", "rice")
    assert line.ingredient.uses == [line]


def test_same_ingredient_twice_in_one_recipe(app, owner_id, ctx):
    recipe = ctx.get(Recipe, add_recipe(app, owner_id, "Adobo", ["1 head garlic", "3 cloves garlic"]))
    assert [line.ingredient.name for line in recipe.ingredients] == ["garlic", "garlic"]


def test_ordering_list_keeps_positions(app, owner_id, ctx):
    recipe = ctx.get(Recipe, add_recipe(app, owner_id, "Soup", steps=["one", "two", "three"]))
    recipe.steps.insert(0, Step(text="zero"))
    ctx.commit()
    ctx.expire_all()
    recipe = ctx.get(Recipe, recipe.id)
    assert [(s.position, s.text) for s in recipe.steps] == [(0, "zero"), (1, "one"), (2, "two"), (3, "three")]


def test_deleting_a_recipe_cascades(app, owner_id, ctx):
    recipe_id = add_recipe(app, owner_id, "Adobo", ["1 kg chicken", "1 head garlic"], tags=["ulam"])
    recipe = ctx.get(Recipe, recipe_id)
    recipe.photo = Photo(data=b"x", mime="image/webp", width=1, height=1, size=1)
    ctx.commit()

    ctx.delete(recipe)
    ctx.commit()
    for table in (RecipeIngredient, Step, Photo, recipe_tags):
        assert count(ctx, table) == 0
    # The tag and the catalog ingredients stay.
    assert ctx.scalar(select(Tag).where(Tag.name == "ulam")) is not None
    assert resolve(ctx, "chicken") is not None


def test_an_ingredient_in_use_cant_be_deleted(app, owner_id, ctx):
    add_recipe(app, owner_id, "Adobo", ["1 kg chicken"])
    chicken = resolve(ctx, "chicken")
    ctx.delete(chicken)
    with pytest.raises(IntegrityError):
        ctx.commit()  # ON DELETE RESTRICT: merge it instead
    ctx.rollback()


def test_deleting_a_user_deletes_everything_of_theirs(app, other_id, ctx):
    add_recipe(app, other_id, "Theirs", ["1 cup rice"], tags=["mine"])
    from sangkap.models import User
    ctx.delete(ctx.get(User, other_id))
    ctx.commit()
    assert count(ctx, Recipe) == 0 and count(ctx, Tag) == 0
    assert count(ctx, Ingredient) > 100  # the shared catalog stays


def test_photo_bytes_are_not_loaded_with_the_recipe(app, owner_id, ctx):
    recipe = ctx.get(Recipe, add_recipe(app, owner_id, "Pic"))
    recipe.photo = Photo(data=b"big bytes", mime="image/webp", width=1, height=1, size=9)
    ctx.commit()
    ctx.expunge_all()
    photo = ctx.get(Recipe, recipe.id).photo
    assert "data" not in photo.__dict__  # deferred: not loaded yet
    assert photo.data == b"big bytes"    # loaded on first use


def test_servings_must_be_sensible(app, owner_id, ctx):
    ctx.add(Recipe(user_id=owner_id, title="Feast", servings=0))
    with pytest.raises(IntegrityError):
        ctx.commit()
    ctx.rollback()


def test_total_minutes():
    assert Recipe(prep_minutes=10, cook_minutes=None).total_minutes == 10
    assert Recipe(prep_minutes=None, cook_minutes=None).total_minutes is None
