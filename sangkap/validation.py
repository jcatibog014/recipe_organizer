"""Check the recipe form: form data in, (data, errors) out. No Flask here.

The ingredient rows come as parallel lists, one item per row in page
order (Flask's request.form.getlist("row_name") etc.):

    row_kind     "item" or "section" ("For the sauce" headings)
    row_section  the heading's text (section rows only)
    row_amount   "1 1/2", "2-3", "" ...
    row_unit     one of quantities.UNITS, or ""
    row_name     "garlic"
    row_note     "minced"
    row_optional "1" or ""

Every row sends every field (some hidden), so the lists stay in step.
"""
import re

from .ingredients import normalize
from .models import NAME_MAX, NOTE_MAX, SECTION_MAX, TAG_MAX, TITLE_MAX, URL_MAX
from .quantities import UNITS, amount_for_input, parse_amount

DESCRIPTION_MAX = 2000
NOTES_MAX = 5000
STEP_MAX = 2000
MAX_ROWS = 80
MAX_STEPS = 40
MAX_TAGS = 12
MAX_MINUTES = 24 * 60
ROW_FIELDS = ("kind", "section", "amount", "unit", "name", "note", "optional")


def blank_row(kind="item"):
    return {"kind": kind, "section": "", "amount": "", "unit": "", "name": "", "note": "",
            "optional": False, "error": ""}


def clean_tag(name):
    """ "  #Quick  Meals " -> "quick meals"."""
    return re.sub(r"\s+", " ", (name or "").strip().lstrip("#").strip().lower())[:TAG_MAX]


def parse_tags(text):
    """ "Soup, quick, soup" -> ["soup", "quick"] (no repeats, in order)."""
    tags = []
    for part in (text or "").split(","):
        tag = clean_tag(part)
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def whole_number(text, low, high):
    """ "45" -> 45; "" -> None; anything else or out of range -> ValueError."""
    text = (text or "").strip()
    if not text:
        return None
    if not text.isdigit() or not low <= int(text) <= high:
        raise ValueError(f"Use a whole number from {low} to {high}.")
    return int(text)


def read_rows(form):
    """The posted ingredient rows, as dicts of the typed text (for showing again)."""
    lists = {field: form.getlist(f"row_{field}") for field in ROW_FIELDS}
    count = max((len(values) for values in lists.values()), default=0)
    rows = []
    for index in range(min(count, MAX_ROWS)):
        def value(field):
            values = lists[field]
            return values[index].strip() if index < len(values) else ""
        row = blank_row("section" if value("kind") == "section" else "item")
        row.update(section=value("section"), amount=value("amount"), unit=value("unit"),
                   name=value("name"), note=value("note"), optional=value("optional") == "1")
        rows.append(row)
    return rows


def rows_from_paste(pasted_rows):
    """paste.parse_block() rows -> form rows (amounts as text for the boxes)."""
    rows = []
    for parsed in pasted_rows:
        if parsed["kind"] == "section":
            row = blank_row("section")
            row["section"] = parsed["section"]
        else:
            row = blank_row()
            row.update(amount=amount_for_input(parsed["amount"], parsed["amount_max"]),
                       unit=parsed["unit"], name=parsed["name"], note=parsed["note"],
                       optional=parsed["is_optional"])
        rows.append(row)
    return rows


def is_blank(row):
    if row["kind"] == "section":
        return not row["section"]
    return not (row["name"] or row["amount"] or row["note"])


def validate_recipe(form):
    """Check the whole form. Returns (data, errors).

    data always has "form_rows" and "form_steps" (what was typed), so the
    form can be shown again with the person's text and the row errors.
    """
    errors = {}
    data = {}

    data["title"] = re.sub(r"\s+", " ", form.get("title", "")).strip()
    if not data["title"]:
        errors["title"] = "Give your recipe a name."
    elif len(data["title"]) > TITLE_MAX:
        errors["title"] = f"Keep the name under {TITLE_MAX} characters."

    data["description"] = form.get("description", "").strip()
    if len(data["description"]) > DESCRIPTION_MAX:
        errors["description"] = f"Keep this under {DESCRIPTION_MAX} characters."
    data["notes"] = form.get("notes", "").strip()
    if len(data["notes"]) > NOTES_MAX:
        errors["notes"] = f"Keep the notes under {NOTES_MAX} characters."

    try:
        data["servings"] = whole_number(form.get("servings"), 1, 100)
        if data["servings"] is None:
            errors["servings"] = "How many people does it feed?"
    except ValueError as error:
        errors["servings"] = str(error)
    for field in ("prep_minutes", "cook_minutes"):
        try:
            data[field] = whole_number(form.get(field), 0, MAX_MINUTES)
        except ValueError as error:
            errors[field] = str(error)

    data["source_url"] = form.get("source_url", "").strip()
    if data["source_url"] and (
        not data["source_url"].startswith(("http://", "https://")) or len(data["source_url"]) > URL_MAX
        or " " in data["source_url"]
    ):
        errors["source_url"] = "Paste a full web address that starts with https://"

    data["tags"] = parse_tags(form.get("tags", ""))
    if len(data["tags"]) > MAX_TAGS:
        errors["tags"] = f"Use at most {MAX_TAGS} tags."

    # Ingredient rows
    form_rows = read_rows(form)
    data["form_rows"] = form_rows
    data["rows"] = []
    section = ""
    for row in form_rows:
        if is_blank(row):
            continue
        if row["kind"] == "section":
            section = row["section"][:SECTION_MAX]
            continue
        try:
            amount, amount_max = parse_amount(row["amount"])
        except ValueError as error:
            row["error"] = str(error)
            continue
        if not normalize(row["name"]):
            row["error"] = "Write what the ingredient is."
        elif len(row["name"]) > NAME_MAX:
            row["error"] = f"Keep the name under {NAME_MAX} characters."
        elif row["unit"] and row["unit"] not in UNITS:
            row["error"] = "Choose a unit from the list."
        elif len(row["note"]) > NOTE_MAX:
            row["error"] = f"Keep the note under {NOTE_MAX} characters."
        else:
            data["rows"].append({
                "section": section, "amount": amount, "amount_max": amount_max,
                "unit": row["unit"], "name": row["name"], "note": row["note"],
                "is_optional": row["optional"],
            })
    if any(row["error"] for row in form_rows):
        errors["rows"] = "Please fix the ingredient rows marked below."

    # Steps
    form_steps = [text.strip() for text in form.getlist("step_text")][:MAX_STEPS]
    data["form_steps"] = form_steps
    data["steps"] = [text for text in form_steps if text]
    if any(len(text) > STEP_MAX for text in data["steps"]):
        errors["steps"] = f"Keep each step under {STEP_MAX} characters."

    return data, errors
