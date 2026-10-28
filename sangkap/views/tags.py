"""Your tags: the plain many-to-many (recipes <-> tags) in action.

Renaming a tag to a name you already use merges the two: every recipe
of the old tag gets the other one, then the old tag is deleted.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from .. import db
from ..auth import login_required
from ..models import Tag, recipe_tags
from ..validation import clean_tag

bp = Blueprint("tags", __name__)


def owned_tag(tag_id):
    tag = db.session().get(Tag, tag_id)
    if tag is None or tag.user_id != g.user.id:
        abort(404)
    return tag


@bp.get("/tags")
@login_required
def index():
    # LEFT JOIN, so a tag with no recipes shows 0 (COUNT of NULLs is 0).
    count = func.count(recipe_tags.c.recipe_id)
    rows = db.session().execute(
        select(Tag, count)
        .outerjoin(recipe_tags, recipe_tags.c.tag_id == Tag.id)
        .where(Tag.user_id == g.user.id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    ).all()
    return render_template("tags.html", rows=rows)


@bp.post("/tags/<int:tag_id>/rename")
@login_required
def rename(tag_id):
    tag = owned_tag(tag_id)
    s = db.session()
    name = clean_tag(request.form.get("name", ""))
    if not name or name == tag.name:
        return redirect(url_for("tags.index"))
    other = s.scalar(select(Tag).where(Tag.user_id == g.user.id, Tag.name == name))
    if other is None:
        tag.name = name
        flash(f"Renamed to #{name}.")
    else:
        for recipe in list(tag.recipes):
            if other not in recipe.tags:
                recipe.tags.append(other)
        s.delete(tag)
        flash(f"Merged into #{name}.")
    s.commit()
    return redirect(url_for("tags.index"))


@bp.post("/tags/<int:tag_id>/delete")
@login_required
def delete(tag_id):
    tag = owned_tag(tag_id)
    s = db.session()
    s.delete(tag)  # its recipe_tags rows go too; the recipes stay
    s.commit()
    flash(f"Deleted #{tag.name}. Your recipes are still there.")
    return redirect(url_for("tags.index"))
