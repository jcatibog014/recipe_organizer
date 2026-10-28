"""Logging in and out, the demo account, and protection for every form.

There is no sign-up page. The owner's account is made on the command line:

    flask --app sangkap create-user <name>

Anyone can press "Try the demo", which logs in as the shared demo user.
Every recipe and tag has a user_id, and every query filters on
g.user.id, so the demo can never see the owner's recipes
(tests/test_auth.py and tests/test_recipes.py check this).
"""
import functools
import hmac
import json
import secrets
from datetime import timedelta

import click
from flask import (
    Blueprint, abort, flash, g, make_response, redirect, render_template, request, session, url_for,
)
from flask.cli import with_appcontext
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .dates import utcnow
from .models import Recipe, User

bp = Blueprint("auth", __name__)

USERNAME_MAX_LENGTH = 40
PASSWORD_MIN_LENGTH = 8
# After 5 wrong passwords in a row, the account waits 15 minutes.
# This makes guessing the owner's password on the live site very slow.
MAX_FAILED_LOGINS = 5
LOCK_TIME = timedelta(minutes=15)

DEMO_USERNAME = "demo"
# Many visitors share the demo. Its recipes are made fresh when someone
# starts the demo and the last reset was more than an hour ago.
DEMO_RESET_AFTER = timedelta(hours=1)

WRONG_LOGIN = "Wrong username or password."


# ---------- Users in the database ----------

def clean_username(text):
    return (text or "").strip().lower()


def find_user(s, username):
    """A real (not demo) user by username, or None."""
    return s.scalar(select(User).where(User.username == clean_username(username), User.is_demo.is_(False)))


def create_user(s, username, password, is_demo=False):
    """Add a user. The caller commits."""
    user = User(username=clean_username(username), password_hash=generate_password_hash(password),
                is_demo=is_demo)
    s.add(user)
    s.flush()
    return user


def set_password(user, password):
    user.password_hash = generate_password_hash(password)
    user.failed_logins = 0
    user.locked_until = None


def check_login(s, username, password, moment):
    """Return (user, None) if the password is right, else (None, message).

    The message never says whether the username exists, so a stranger
    can't use the login form to find out the owner's username.
    """
    user = find_user(s, username)
    if user is None:
        return None, WRONG_LOGIN

    if user.locked_until and user.locked_until > moment:
        return None, "Too many failed attempts. Please wait 15 minutes and try again."

    if not check_password_hash(user.password_hash, password or ""):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.failed_logins, user.locked_until = 0, moment + LOCK_TIME
        s.commit()
        return None, WRONG_LOGIN

    user.failed_logins, user.locked_until = 0, None
    s.commit()
    return user, None


def demo_user(s, moment, force_reset=False):
    """The demo user, made (or made fresh) when needed. The caller commits."""
    from . import seed

    user = s.scalar(select(User).where(User.is_demo.is_(True)))
    if user is None:
        # Nobody knows this password: the demo is only opened with the button.
        user = create_user(s, DEMO_USERNAME, secrets.token_urlsafe(32), is_demo=True)

    if force_reset or user.demo_reset_at is None or user.demo_reset_at < moment - DEMO_RESET_AFTER:
        seed.reset_demo(s, user)
        user.demo_reset_at = moment
    return user


def safe_next(target, default=None):
    """Only go back to a page on this site (after logging in or saving a form).

    "/recipes/3" is fine. "https://evil.example" and "//evil.example"
    are not: a fake link could send people there after a real login.
    """
    if target and target.startswith("/") and not target.startswith(("//", "/\\")):
        return target
    return default or url_for("recipes.index")


def log_in(user):
    session.clear()  # a new session for the new user (old cookies can't be reused)
    session.permanent = True  # stay logged in for PERMANENT_SESSION_LIFETIME
    session["user_id"] = user.id


# ---------- Every request ----------

@bp.before_app_request
def load_user():
    user_id = session.get("user_id")
    g.user = db.session().get(User, user_id) if user_id is not None else None


def csrf_token():
    """A secret per session, put into every form as a hidden field.

    Another website could make your browser send a form to this site (your
    login cookie goes with it). It can't read this secret, so its form fails.
    """
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


@bp.before_app_request
def check_csrf():
    if request.method != "POST":
        return
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf", "")
    # compare_digest takes the same time for every wrong guess.
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "This form has expired. Please go back, reload the page and try again.")


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


# ---------- Pages ----------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("recipes.index"))
    next_page = request.values.get("next", "")
    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "")[:USERNAME_MAX_LENGTH]
        user, error = check_login(db.session(), username, request.form.get("password", ""), utcnow())
        if user:
            log_in(user)
            return redirect(safe_next(next_page))
    status = 401 if error else 200
    return render_template("login.html", error=error, username=username, next=next_page), status


@bp.post("/demo")
def demo():
    s = db.session()
    user = demo_user(s, utcnow())
    s.commit()
    log_in(user)
    flash("Welcome to the demo! The recipes here are samples, so feel free to try anything.")
    return redirect(url_for("recipes.index"))


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have logged out. See you next meal!")
    return redirect(url_for("auth.login"))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    errors = {}
    if request.method == "POST":
        if g.user.is_demo:
            abort(403, "The demo account can't change its password.")
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        if not check_password_hash(g.user.password_hash, current):
            errors["current_password"] = "That isn't your current password."
        if len(new) < PASSWORD_MIN_LENGTH:
            errors["new_password"] = f"Use at least {PASSWORD_MIN_LENGTH} characters."
        elif new != request.form.get("confirm_password", ""):
            errors["confirm_password"] = "The two new passwords are not the same."
        if not errors:
            set_password(g.user, new)
            db.session().commit()
            flash("Your password has been changed.")
            return redirect(url_for("auth.settings"))
    return render_template("settings.html", errors=errors), 400 if errors else 200


@bp.get("/settings/export")
@login_required
def export():
    """Download every recipe as one JSON file: a backup you can keep."""
    recipes = db.session().scalars(
        select(Recipe).where(Recipe.user_id == g.user.id).order_by(Recipe.title)
    ).all()
    data = {
        "app": "Sangkap",
        "exported_at": utcnow().isoformat(timespec="seconds") + "Z",
        "recipes": [
            {
                "title": r.title, "description": r.description, "servings": r.servings,
                "prep_minutes": r.prep_minutes, "cook_minutes": r.cook_minutes,
                "tags": [tag.name for tag in r.tags], "favorite": r.is_favorite,
                "ingredients": [
                    {"section": line.section, "amount": line.amount, "amount_max": line.amount_max,
                     "unit": line.unit, "name": line.ingredient.name, "note": line.note,
                     "optional": line.is_optional}
                    for line in r.ingredients
                ],
                "steps": [step.text for step in r.steps],
                "notes": r.notes, "source_url": r.source_url, "source": r.source,
                "created_at": r.created_at.isoformat(timespec="seconds") + "Z",
            }
            for r in recipes
        ],
    }
    response = make_response(json.dumps(data, ensure_ascii=False, indent=2))
    response.mimetype = "application/json"
    filename = f"sangkap-recipes-{utcnow():%Y-%m-%d}.json"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ---------- Command line ----------

def ask_password():
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    if len(password) < PASSWORD_MIN_LENGTH:
        raise click.ClickException(f"Use at least {PASSWORD_MIN_LENGTH} characters.")
    return password


@click.command("create-user")
@with_appcontext
@click.argument("username")
def create_user_command(username):
    """Make a login."""
    s = db.session()
    username = clean_username(username)
    if not username or len(username) > USERNAME_MAX_LENGTH:
        raise click.ClickException(f"Use 1 to {USERNAME_MAX_LENGTH} characters for the username.")
    if username == DEMO_USERNAME:
        raise click.ClickException('"demo" is kept for the demo account.')
    if s.scalar(select(User).where(User.username == username)):
        raise click.ClickException(f'"{username}" already exists. Use set-password to change the password.')
    create_user(s, username, ask_password())
    s.commit()
    click.echo(f'Made the user "{username}".')


@click.command("set-password")
@with_appcontext
@click.argument("username")
def set_password_command(username):
    """Change a user's password (and unlock the account)."""
    s = db.session()
    user = find_user(s, username)
    if user is None:
        raise click.ClickException(f'There is no user "{username}".')
    set_password(user, ask_password())
    s.commit()
    click.echo("The password is changed.")


@click.command("reset-demo")
@with_appcontext
def reset_demo_command():
    """Make the demo recipes fresh now."""
    s = db.session()
    demo_user(s, utcnow(), force_reset=True)
    s.commit()
    click.echo("The demo recipes are fresh.")


def init_app(app):
    app.jinja_env.globals["csrf_token"] = csrf_token
    for command in (create_user_command, set_password_command, reset_demo_command):
        app.cli.add_command(command)
