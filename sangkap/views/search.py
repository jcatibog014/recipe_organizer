"""The search page: find your recipes by the ingredients you have.

It is a GET form, so every search has its own address you can bookmark:
/search?have=chicken,garlic&mode=pantry&missing=1
"""
from flask import Blueprint, g, render_template, request, url_for
from sqlalchemy import select

from .. import db, ingredients, search
from ..auth import login_required
from ..models import Tag

bp = Blueprint("search", __name__)

MINUTE_CHOICES = (15, 30, 45, 60, 90, 120)


def split_names(text):
    """ "chicken, Garlic ,, gata" -> ["chicken", "garlic", "gata"] (no repeats)."""
    names = []
    for part in (text or "").split(","):
        name = ingredients.normalize(part)
        if name and name not in names:
            names.append(name)
    return names[:search.MAX_INGREDIENTS]


def resolve_names(s, names):
    """Names -> (ingredient ids, [(typed name, ingredient or None)])."""
    found = []
    ids = []
    for name in names:
        ingredient = ingredients.resolve(s, name)
        found.append((name, ingredient))
        if ingredient is not None and ingredient.id not in ids:
            ids.append(ingredient.id)
    return ids, found


def chip_links(args, key, names):
    """For each name, the address of this same search without it (the chip's ✕)."""
    links = []
    for name in names:
        rest = [other for other in names if other != name]
        new_args = {k: v for k, v in args.items() if k != key}
        if rest:
            new_args[key] = ", ".join(rest)
        links.append(url_for("search.index", **new_args))
    return links


@bp.get("/search")
@login_required
def index():
    s = db.session()
    args = request.args.to_dict()
    have_names = split_names(args.get("have"))
    without_names = split_names(args.get("without"))
    have_ids, have_found = resolve_names(s, have_names)
    without_ids, without_found = resolve_names(s, without_names)

    mode = args.get("mode", "all")
    if mode not in search.MODES:
        mode = "all"
    try:
        missing_max = max(0, min(3, int(args.get("missing", "1"))))
    except ValueError:
        missing_max = 1
    try:
        max_minutes = int(args.get("time", ""))
        if max_minutes not in MINUTE_CHOICES:
            max_minutes = None
    except ValueError:
        max_minutes = None

    my_tags = s.scalars(select(Tag).where(Tag.user_id == g.user.id).order_by(Tag.name)).all()
    tag_ids = [tag.id for tag in my_tags if str(tag.id) in request.args.getlist("tag")]

    # A ticked box sends "staples=1" and an unticked one sends nothing, so the
    # form also sends "sent=1": then a missing "staples" means "unticked".
    # A plain link (no "sent") gets the default: on.
    use_staples = args.get("staples") == "1" or "sent" not in args
    staple_ids = resolve_names(s, search.STAPLES)[0] if use_staples else []
    q = search.Query(
        have=have_ids, without=without_ids, mode=mode, missing_max=missing_max,
        text=args.get("q", "").strip()[:100], tag_ids=tag_ids, max_minutes=max_minutes,
        favorites=args.get("favorites") == "1", staples=staple_ids,
    )
    unknown = [name for name, ingredient in have_found + without_found if ingredient is None]
    # Typing only names we don't know means "nothing matches", not "show everything".
    nothing_known = bool(have_names) and not have_ids
    results = None
    if not q.is_empty() or have_names:
        results = [] if nothing_known else search.run(s, g.user.id, q)

    popular = [ingredient for ingredient, _count in ingredients.usage(s, g.user.id)
               if ingredient.name not in have_names and ingredient.name not in search.STAPLES][:14]
    return render_template(
        "search.html",
        q=q, args=args, results=results, unknown=unknown,
        have=list(zip(have_names, chip_links(args, "have", have_names))),
        without=list(zip(without_names, chip_links(args, "without", without_names))),
        have_text=", ".join(have_names), without_text=", ".join(without_names),
        my_tags=my_tags, minute_choices=MINUTE_CHOICES, popular=popular,
        use_staples=use_staples, staples=search.STAPLES,
        suggestions=ingredients.suggestions(s, g.user.id),
    )
