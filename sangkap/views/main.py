"""Pages that aren't about one thing: the health check, the service worker and the style board."""
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


@bp.get("/sw.js")
def service_worker():
    """The service worker (it makes Sangkap installable on a phone).

    It's served from the top of the site, not /static/, because a service
    worker only looks after the pages below the address it came from.
    """
    response = current_app.send_static_file("sw.js")
    response.headers["Cache-Control"] = "no-cache"  # always check for a new version
    return response


@bp.get("/styleguide")
def styleguide():
    """Every colour, button, chip and card on one page (only while developing)."""
    if not (current_app.debug or current_app.testing):
        abort(404)
    samples = [name for name, _kind, _aliases in CATALOG[:12]]
    return render_template("styleguide.html", samples=samples)
