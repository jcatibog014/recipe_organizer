import json
import os
from pathlib import Path

import pytest

from sangkap import auth, create_app, db, ingredients, mealdb
from sangkap.models import Recipe, RecipeIngredient, Step, Tag

# Tests use a fresh SQLite file per test. To check everything on PostgreSQL
# too, set TEST_DATABASE_URL to an EMPTY Neon branch (its tables are dropped
# and made again for every test, so never point it at the live database).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
FIXTURES = Path(__file__).parent / "fixtures" / "mealdb"

CSRF = "test-csrf-token"
OWNER = "juan"
OWNER_PASSWORD = "correct horse"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE": str(tmp_path / "test.sqlite"),
        "DATABASE_URL": TEST_DATABASE_URL,
    })
    with app.app_context():
        if TEST_DATABASE_URL:
            db.drop_tables()
        db.create_tables()
        s = db.session()
        ingredients.add_catalog(s)
        auth.create_user(s, OWNER, OWNER_PASSWORD)
        s.commit()
    return app


@pytest.fixture
def ctx(app):
    """An app context, for tests that use db.session() directly."""
    with app.app_context():
        yield db.session()


@pytest.fixture
def client(app):
    client = app.test_client()
    # Every POST needs the session's CSRF token. Put a known one in the session.
    with client.session_transaction() as session:
        session["csrf"] = CSRF
    return client


def post(client, url, data=None, **kwargs):
    """POST a form with the right CSRF token, like a real page would."""
    # Logging in or out starts a new session (and a new token), so set it every time.
    with client.session_transaction() as session:
        session["csrf"] = CSRF
    return client.post(url, data={"csrf_token": CSRF, **(data or {})}, **kwargs)


def log_in_as(client, user_id):
    """Skip the login form: put the user straight into the session."""
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["csrf"] = CSRF


def user_id(app, username):
    from sqlalchemy import select
    from sangkap.models import User
    with app.app_context():
        return db.session().scalar(select(User.id).where(User.username == username))


def make_user(app, username):
    with app.app_context():
        s = db.session()
        user = auth.create_user(s, username, "another password")
        s.commit()
        return user.id


def add_recipe(app, owner_id, title, lines=(), tags=(), steps=("Cook it.",), **fields):
    """Put a recipe straight into the database. lines: "1 cup rice" style text,
    or (text, {"is_optional": True}) pairs. Returns its id."""
    from sqlalchemy import select

    from sangkap import paste
    with app.app_context():
        s = db.session()
        rows = []
        for line in lines:
            text, extra = (line, {}) if isinstance(line, str) else line
            row = paste.parse_line(text)
            row.update(extra)
            rows.append((row, ingredients.get_or_create(s, row["name"])))
        found_tags = [s.scalar(select(Tag).where(Tag.user_id == owner_id, Tag.name == name))
                      or Tag(user_id=owner_id, name=name) for name in tags]
        with s.no_autoflush:
            recipe = Recipe(user_id=owner_id, title=title, servings=fields.pop("servings", 4), **fields)
            recipe.ingredients = [
                RecipeIngredient(ingredient=ingredient, amount=row["amount"], amount_max=row["amount_max"],
                                 unit=row["unit"], note=row["note"], is_optional=row["is_optional"],
                                 position=position)
                for position, (row, ingredient) in enumerate(rows)
            ]
            recipe.tags = found_tags
            recipe.steps = [Step(text=text, position=i) for i, text in enumerate(steps)]
            s.add(recipe)
        s.commit()
        return recipe.id


@pytest.fixture
def owner_id(app):
    return user_id(app, OWNER)


@pytest.fixture
def other_id(app):
    """A second user, to check that nobody sees another user's recipes."""
    return make_user(app, "pedro")


@pytest.fixture
def owner_client(client, owner_id):
    log_in_as(client, owner_id)
    return client


# ---------- TheMealDB without the internet ----------

def fixture_for(url):
    """Which saved answer in tests/fixtures/mealdb/ fits this TheMealDB address."""
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url)
    endpoint = parsed.path.rsplit("/", 1)[-1]
    query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    if endpoint == "lookup.php":
        name = f"lookup_{query['i']}.json"
    elif endpoint == "search.php":
        name = f"search_{query['s'].lower()}.json"
    elif endpoint == "list.php":
        name = {"a": "list_areas.json", "c": "list_categories.json", "i": "list_ingredients.json"}[next(iter(query))]
    elif "a" in query:
        name = f"area_{query['a'].lower()}.json"
    elif "c" in query:
        name = f"category_{query['c'].lower()}.json"
    else:
        name = f"ingredient_{query['i'].lower()}.json"
    path = FIXTURES / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"meals": None}


@pytest.fixture(autouse=True)
def offline_mealdb(monkeypatch):
    """No test ever calls the real TheMealDB: answers come from the fixture files."""
    calls = []

    def fake_json(url):
        calls.append(url)
        return fixture_for(url)

    def fake_bytes(url):
        calls.append(url)
        raise OSError("no pictures in tests")

    mealdb.clear_cache()
    monkeypatch.setattr(mealdb, "FETCH_JSON", fake_json)
    monkeypatch.setattr(mealdb, "FETCH_BYTES", fake_bytes)
    return calls
