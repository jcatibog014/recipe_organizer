"""Pages that aren't about one thing: the health check and the style board."""
from flask import Blueprint, abort, current_app, render_template
from sqlalchemy import text

from .. import db
from ..ingredients import CATALOG

bp = Blueprint("main", __name__)


@bp.get("/healthz")
def healthz():
    """Render calls this to check the site is up (and can reach the database)."""
    db.session().execute(text("SELECT 1"))
    return {"ok": True}


@bp.get("/styleguide")
def styleguide():
    """Every colour, button, chip and card on one page (only while developing)."""
    if not (current_app.debug or current_app.testing):
        abort(404)
    samples = [(name, emoji) for name, _kind, emoji, _aliases in CATALOG[:12]]
    return render_template("styleguide.html", samples=samples)
