from datetime import timedelta

from sqlalchemy import func, select

from sangkap import auth, db
from sangkap.dates import utcnow
from sangkap.models import PlanEntry, Recipe, User
from sangkap.seed import DEMO_RECIPES

from conftest import CSRF, OWNER, OWNER_PASSWORD, add_recipe, post


def test_pages_need_login(client):
    for url in ["/", "/recipes/new", "/search", "/discover", "/plan", "/ingredients", "/ingredients/manage",
                "/tags", "/settings"]:
        response = client.get(url)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_login_and_logout(client):
    response = post(client, "/login", {"username": "  JUAN ", "password": OWNER_PASSWORD})
    assert response.status_code == 302
    assert client.get("/").status_code == 200
    post(client, "/logout")
    assert client.get("/").status_code == 302


def test_wrong_password_says_the_same_as_unknown_user(client):
    wrong = post(client, "/login", {"username": OWNER, "password": "nope"})
    unknown = post(client, "/login", {"username": "nobody", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert auth.WRONG_LOGIN.encode() in wrong.data and auth.WRONG_LOGIN.encode() in unknown.data


def test_five_wrong_passwords_lock_the_account(app, client):
    for _ in range(auth.MAX_FAILED_LOGINS):
        post(client, "/login", {"username": OWNER, "password": "nope"})
    response = post(client, "/login", {"username": OWNER, "password": OWNER_PASSWORD})
    assert b"Too many failed attempts" in response.data
    with app.app_context():
        user = auth.find_user(db.session(), OWNER)
        assert user.locked_until > utcnow() + timedelta(minutes=14)


def test_login_goes_back_only_to_this_site(client):
    response = post(client, "/login", {"username": OWNER, "password": OWNER_PASSWORD, "next": "//evil.example"})
    assert response.headers["Location"] == "/"
    post(client, "/logout")
    response = post(client, "/login", {"username": OWNER, "password": OWNER_PASSWORD, "next": "/plan"})
    assert response.headers["Location"] == "/plan"


def test_post_without_csrf_is_refused(owner_client):
    response = owner_client.post("/recipes/new", data={"title": "x", "csrf_token": "wrong"})
    assert response.status_code == 400
    assert CSRF  # (the right one is used by post())


def test_demo_login_makes_sample_recipes_and_a_plan(app, client):
    response = post(client, "/demo")
    assert response.status_code == 302
    page = client.get("/").data.decode()
    assert "Chicken Adobo" in page and "Leche Flan" in page and "demo" in page
    with app.app_context():
        s = db.session()
        demo = s.scalar(select(User).where(User.is_demo.is_(True)))
        assert s.scalar(select(func.count()).select_from(Recipe).where(Recipe.user_id == demo.id)) == len(DEMO_RECIPES)
        assert s.scalar(select(func.count()).select_from(PlanEntry).where(PlanEntry.user_id == demo.id)) == 7


def test_demo_resets_after_an_hour(app, client):
    post(client, "/demo")
    with app.app_context():
        s = db.session()
        demo = s.scalar(select(User).where(User.is_demo.is_(True)))
        add_recipe(app, demo.id, "Visitor's junk", ["1 cup glitter"])
        auth.demo_user(s, utcnow())  # less than an hour: kept
        s.commit()
        assert s.scalar(select(Recipe).where(Recipe.title == "Visitor's junk")) is not None
        auth.demo_user(s, utcnow() + timedelta(hours=2))
        s.commit()
        assert s.scalar(select(Recipe).where(Recipe.title == "Visitor's junk")) is None
        from sangkap.ingredients import resolve
        assert resolve(s, "glitter") is None  # its odd ingredient is cleaned up too


def test_demo_cant_log_in_with_a_password(app, client):
    post(client, "/demo")
    post(client, "/logout")
    response = post(client, "/login", {"username": "demo", "password": ""})
    assert response.status_code == 401


def test_change_password(owner_client):
    bad = post(owner_client, "/settings", {"current_password": "nope", "new_password": "short",
                                           "confirm_password": "short"})
    assert bad.status_code == 400
    good = post(owner_client, "/settings", {"current_password": OWNER_PASSWORD, "new_password": "new password!",
                                            "confirm_password": "new password!"})
    assert good.status_code == 302


def test_demo_cant_change_password(client):
    post(client, "/demo")
    response = post(client, "/settings", {"current_password": "", "new_password": "whatever1",
                                          "confirm_password": "whatever1"})
    assert response.status_code == 403


def test_cli_create_user(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-user", "Maria"], input="a good password\na good password\n")
    assert result.exit_code == 0, result.output
    assert runner.invoke(args=["create-user", "maria"], input="x\nx\n").exit_code != 0
    assert runner.invoke(args=["create-user", "demo"], input="a good password\na good password\n").exit_code != 0


def test_security_headers(client):
    response = client.get("/login")
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"


def test_healthz(client):
    assert client.get("/healthz").json == {"ok": True}


def test_export_is_a_json_backup_of_only_my_recipes(app, owner_client, owner_id, other_id):
    add_recipe(app, owner_id, "Mine", ["1 cup rice"], tags=["quick"])
    add_recipe(app, other_id, "Not mine")
    response = owner_client.get("/settings/export")
    assert "attachment" in response.headers["Content-Disposition"]
    data = response.get_json(force=True)
    assert [r["title"] for r in data["recipes"]] == ["Mine"]
    assert data["recipes"][0]["ingredients"][0] == {"section": "", "amount": 1.0, "amount_max": None,
                                                    "unit": "cup", "name": "rice", "note": "",
                                                    "optional": False}


def test_settings_page(owner_client, client):
    page = owner_client.get("/settings").data.decode()
    # Three rows in "Your recipe box", each with its own button, then the account.
    assert page.count('class="setting-row"') == 5  # tags, ingredients, backup, install, logged in as
    for label in ("Manage Tags", "Manage Ingredients", "Download backup", "Log out", "Change password"):
        assert label in page
    assert "Logged In As" in page and OWNER in page
    assert 'name="current_password"' in page


def test_settings_page_for_the_demo(client):
    post(client, "/demo")
    page = client.get("/settings").data.decode()
    assert "the shared demo account" in page and "can't change its password" in page
    assert 'name="current_password"' not in page


def test_installable_as_an_app(client, owner_client):
    # The service worker is served from the top of the site, never cached for long.
    worker = client.get("/sw.js")
    assert worker.status_code == 200 and "javascript" in worker.mimetype
    assert worker.headers["Cache-Control"] == "no-cache" and b"sangkap-v1" in worker.data
    # It is allowed by the Content-Security-Policy, and its files exist.
    assert "worker-src 'self'" in worker.headers["Content-Security-Policy"]
    for path in ("/static/offline.html", "/static/site.webmanifest", "/static/icons/icon-192.png",
                 "/static/icons/icon-512.png"):
        assert client.get(path).status_code == 200, path
    manifest = client.get("/static/site.webmanifest").get_json(force=True)
    assert manifest["display"] == "standalone" and manifest["scope"] == "/"
    # The Install buttons are in the page (hidden until the browser offers to install),
    # and Settings explains the iPhone way too.
    page = owner_client.get("/settings").data.decode()
    assert page.count("data-install hidden") == 2
    assert "Add to Home Screen" in page
