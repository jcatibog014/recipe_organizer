import re

from conftest import add_recipe, post


def share(client, recipe_id):
    post(client, f"/recipes/{recipe_id}/share")
    page = client.get(f"/recipes/{recipe_id}").data.decode()
    match = re.search(r"/r/([\w-]+)", page)
    return match.group(1) if match else None


def test_shared_link_works_without_login(app, owner_client, owner_id):
    recipe_id = add_recipe(app, owner_id, "Lola's Adobo", ["1 kg chicken"], notes="SECRET NOTE")
    code = share(owner_client, recipe_id)
    assert code and len(code) >= 12

    stranger = app.test_client()
    response = stranger.get(f"/r/{code}")
    page = response.data.decode()
    assert response.status_code == 200
    assert "Adobo" in page and "chicken" in page
    assert "SECRET NOTE" not in page and "juan" not in page  # no notes, no owner
    assert response.headers["X-Robots-Tag"] == "noindex"
    assert 'href="/recipes/' not in page  # no edit links
    assert stranger.get(f"/r/{code}?servings=8").status_code == 200
    assert stranger.get(f"/r/{code}/cook").status_code == 200


def test_turning_sharing_off_kills_the_link(app, owner_client, owner_id):
    recipe_id = add_recipe(app, owner_id, "Adobo")
    code = share(owner_client, recipe_id)
    post(owner_client, f"/recipes/{recipe_id}/share")  # off
    assert app.test_client().get(f"/r/{code}").status_code == 404
    new_code = share(owner_client, recipe_id)          # on again: a new link
    assert new_code != code


def test_unknown_codes_are_not_found(client):
    assert client.get("/r/nope").status_code == 404
    assert client.get("/r/nope/photo").status_code == 404
