"""Turn a pasted ingredient list into form rows.

    For the sauce:
    - 3 cloves garlic, minced
    - 1 ½ cups coconut milk (gata)
    - salt to taste
    - 2-3 pcs siling labuyo (optional)

becomes a section "For the sauce" and four rows with amount, unit, name,
note and "optional". Plain Python (see tests/test_paste.py).
"""
import re

from .models import NAME_MAX, NOTE_MAX, SECTION_MAX
from .quantities import split_quantity

MAX_LINES = 80

BULLET = re.compile(r"^\s*(?:[-*•·▢□☐]+|\d+[.)])\s+")
OPTIONAL = re.compile(r"\s*(?:\(\s*optional\s*\)|,?\s*\boptional\b)\s*", re.IGNORECASE)
TO_TASTE = re.compile(r"\s*,?\s*\b(?:to taste|as needed|as desired)\b\s*", re.IGNORECASE)
PARENS = re.compile(r"\s*\(([^)]*)\)\s*")


def parse_line(line):
    """One line -> a row dict, or None for a blank line."""
    line = BULLET.sub("", line.strip()).strip()
    if not line:
        return None

    # "For the sauce:" (a heading, not an ingredient)
    if line.endswith(":") and not line[0].isdigit():
        return {"kind": "section", "section": line.rstrip(":").strip()[:SECTION_MAX]}

    is_optional = bool(OPTIONAL.search(line))
    line = OPTIONAL.sub(" ", line).strip()
    notes = []
    if TO_TASTE.search(line):
        line = TO_TASTE.sub(" ", line).strip()
        notes.append("to taste")

    amount, amount_max, unit, rest = split_quantity(line)

    # "(gata)" and ", minced" are notes; the rest is the ingredient's name.
    for found in PARENS.findall(rest):
        if found.strip():
            notes.insert(0, found.strip())
    rest = PARENS.sub(" ", rest).strip()
    name, _comma, after = rest.partition(",")
    if after.strip():
        notes.insert(0, after.strip())

    return {
        "kind": "item",
        "amount": amount,
        "amount_max": amount_max,
        "unit": unit,
        "name": re.sub(r"\s+", " ", name).strip()[:NAME_MAX],
        "note": ", ".join(notes)[:NOTE_MAX],
        "is_optional": is_optional,
    }


def parse_block(text):
    """Every non-blank line of a pasted list (up to MAX_LINES)."""
    rows = []
    for line in (text or "").splitlines()[:MAX_LINES]:
        row = parse_line(line)
        if row and (row["kind"] == "section" or row["name"]):
            rows.append(row)
    return rows
