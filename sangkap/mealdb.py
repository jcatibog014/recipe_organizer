"""TheMealDB (https://www.themealdb.com/), a free recipe API, for Discover.

We use the free key "1", which TheMealDB allows "for development or for
educational use". Only the server calls it, and answers are kept in memory
for a while (CACHE), so the API isn't asked the same thing twice.

The free key filters by ONE ingredient per call. For "chicken AND garlic"
we call once per ingredient and keep the ids found in every answer.

to_recipe() is the data-modeling lesson: TheMealDB keeps a recipe in one
flat row (strIngredient1..20 + strMeasure1..20, one text of instructions).
We turn that into our tables: lines with amount + unit + ingredient, and steps.
No Flask here (see tests/test_mealdb.py, which never uses the internet).
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .ingredients import normalize
from .models import NOTE_MAX, TITLE_MAX
from .quantities import split_quantity
from .validation import clean_tag

BASE = "https://www.themealdb.com/api/json/v1/1/"
SITE = "https://www.themealdb.com/"
CREDIT = "Recipe data and imagery: TheMealDB"
TIMEOUT = 6  # seconds
HOUR = 60 * 60
DAY = 24 * HOUR
MAX_CACHE = 400
MAX_IMAGE_BYTES = 5 * 1024 * 1024
DEFAULT_SERVINGS = 4  # TheMealDB doesn't say; most of its recipes feed about 4
SLOTS = 20

_cache = {}  # address -> (time it goes stale, answer)


class MealDBError(Exception):
    """TheMealDB couldn't be reached or answered strangely."""


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Sangkap recipe organizer"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bytes(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Sangkap recipe organizer"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = response.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise MealDBError("The picture is too big.")
    return data


# Tests swap these for functions that read tests/fixtures/mealdb/.
FETCH_JSON = fetch_json
FETCH_BYTES = fetch_bytes


def get(endpoint, params, ttl):
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    now = time.monotonic()
    cached = _cache.get(url)
    if cached and cached[0] > now:
        return cached[1]
    try:
        data = FETCH_JSON(url)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise MealDBError(str(error)) from error
    if not isinstance(data, dict):
        raise MealDBError("TheMealDB sent something we didn't expect.")
    if len(_cache) >= MAX_CACHE:
        _cache.clear()  # simple: start again rather than track the oldest
    _cache[url] = (now + ttl, data)
    return data


def clear_cache():
    _cache.clear()


# ---------- Asking TheMealDB ----------

def summaries(data):
    """A list answer -> [{"id", "name", "thumb"}] (thumb is "" if it isn't TheMealDB's)."""
    meals = data.get("meals") or []
    if not isinstance(meals, list):
        return []
    return [
        {"id": str(meal.get("idMeal", "")), "name": meal.get("strMeal") or "", "thumb": image_url(meal)}
        for meal in meals
        if isinstance(meal, dict) and str(meal.get("idMeal", "")).isdigit()
    ]


def search_name(text):
    return summaries(get("search.php", {"s": text}, HOUR))


def by_ingredient(name):
    # TheMealDB writes "chicken_breast" for "chicken breast" in this filter.
    return summaries(get("filter.php", {"i": name.replace(" ", "_")}, HOUR))


def by_area(area):
    return summaries(get("filter.php", {"a": area}, DAY))


def by_category(category):
    return summaries(get("filter.php", {"c": category}, DAY))


def lookup(meal_id):
    """One whole recipe (TheMealDB's dict), or None if there's no such id."""
    if not str(meal_id).isdigit():
        return None
    meals = get("lookup.php", {"i": meal_id}, DAY).get("meals") or []
    return meals[0] if meals and isinstance(meals[0], dict) else None


def list_areas():
    data = get("list.php", {"a": "list"}, DAY)
    return sorted(m["strArea"] for m in data.get("meals") or [] if m.get("strArea"))


def list_categories():
    data = get("list.php", {"c": "list"}, DAY)
    return sorted(m["strCategory"] for m in data.get("meals") or [] if m.get("strCategory"))


def known_ingredients():
    """TheMealDB's own ingredient names, lower-case."""
    data = get("list.php", {"i": "list"}, DAY)
    return {normalize(m["strIngredient"]) for m in data.get("meals") or [] if m.get("strIngredient")}


def best_name(candidates):
    """Our name and its aliases -> the one TheMealDB knows.

    It says "aubergine" and "spring onions" where we say eggplant and green onion.
    """
    try:
        known = known_ingredients()
    except MealDBError:
        return candidates[0]
    for name in candidates:
        if normalize(name) in known:
            return name
    return candidates[0]


def by_ingredients(candidate_lists):
    """Meals that have every ingredient. Each item is [name, alias, alias...]."""
    found = None
    for candidates in candidate_lists:
        meals = by_ingredient(best_name(candidates))
        if found is None:
            found = {meal["id"]: meal for meal in meals}
        else:
            ids = {meal["id"] for meal in meals}
            found = {meal_id: meal for meal_id, meal in found.items() if meal_id in ids}
    return sorted((found or {}).values(), key=lambda meal: meal["name"])


# ---------- TheMealDB's flat row -> our shape ----------

def image_url(meal, size=None):
    """The meal's picture, only if it is on TheMealDB's site (our CSP allows only that)."""
    url = meal.get("strMealThumb") or ""
    if not url.startswith(SITE):
        return ""
    return f"{url}/{size}" if size else url


STEP_MARKER = re.compile(r"^\s*(?:step\s*\d+\s*[:.)-]?|\d+\s*[.):-]|[-•*▪])\s*", re.IGNORECASE)


def split_steps(text):
    """The one long instructions text -> a list of steps."""
    steps = []
    for line in re.split(r"[\r\n]+", text or ""):
        line = STEP_MARKER.sub("", line).strip()
        if line:
            steps.append(line)
    if len(steps) == 1 and len(steps[0]) > 400:
        # One huge paragraph: two sentences per step reads better.
        sentences = re.split(r"(?<=[.!?])\s+", steps[0])
        steps = [" ".join(sentences[i:i + 2]) for i in range(0, len(sentences), 2)]
    return steps


def to_recipe(meal):
    """TheMealDB's dict -> a dict shaped like our Recipe (rows, steps, tags...)."""
    rows = []
    for slot in range(1, SLOTS + 1):
        name = normalize(meal.get(f"strIngredient{slot}") or "")
        if not name:
            continue
        measure = re.sub(r"\s+", " ", (meal.get(f"strMeasure{slot}") or "")).strip()
        amount, amount_max, unit, rest = split_quantity(measure)
        note = rest if (amount is not None or unit) else measure  # "to taste", "Dash"
        rows.append({"name": name, "amount": amount, "amount_max": amount_max, "unit": unit,
                     "note": note[:NOTE_MAX], "is_optional": False, "section": ""})

    tags = []
    for word in [meal.get("strArea"), meal.get("strCategory"), *(meal.get("strTags") or "").split(",")]:
        tag = clean_tag(word or "")
        if tag and tag not in tags and tag != "unknown":
            tags.append(tag)

    area, category = meal.get("strArea") or "", meal.get("strCategory") or ""
    kind = " ".join(part for part in (area, category.lower()) if part)
    meal_id = str(meal.get("idMeal", ""))
    return {
        "id": meal_id,
        "title": (meal.get("strMeal") or "Untitled")[:TITLE_MAX],
        "description": f"A {kind} recipe from TheMealDB." if kind else "A recipe from TheMealDB.",
        "servings": DEFAULT_SERVINGS,
        "prep_minutes": None,
        "cook_minutes": None,
        "tags": tags,
        "ingredients": rows,
        "steps": split_steps(meal.get("strInstructions")),
        "source_url": (meal.get("strSource") or "").strip() or f"{SITE}meal/{meal_id}",
        "youtube": (meal.get("strYoutube") or "").strip(),
        "image": image_url(meal),
    }
