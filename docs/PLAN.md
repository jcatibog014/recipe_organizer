# Roadmap: "Sangkap", a recipe organizer

The plan agreed on 2026-10-28. At the owner's request, **all 7 stages went into one pull request**
(one commit per stage), without stopping for confirmation between stages.

## Context

This is a learning project for the empty repo https://github.com/jcatibog014/recipe_organizer.
It stores recipes (ingredients, amounts, steps, photos) and finds them **by ingredient**: "What can I cook with chicken, garlic and gata?"
The skills to practise are **data modeling, search, and many-to-many relationships**.
It follows the conventions of the other Workspace apps (Flask, plain-function modules, pytest, `.venv`, `AGENTS.md` + `CLAUDE.md`, Render deploy). Login, demo, CSRF and the deploy setup come from `Documents\Workspace\expense_tracker` (Ang Gastos!).

What the owner decided:
- The name is **"Sangkap"** ("ingredient").
- **SQLAlchemy 2.0 ORM + Alembic** (new this time; Ang Gastos! used raw SQL). The data model lives in Python classes.
- **Look: bright kawaii** with a **puffy 3D candy UI** (jelly buttons, pillow cards, glossy chips), **light and dark mode** with a ☀️/🌙 switch.
  The kawaii pictures are a **scattered-ingredients background** at 40% (25% in dark): one AI-made 3D tile that the owner makes from `docs/ART_PROMPTS.md`
  (no image API), turned into WebP by `docs/make_background.py`. Until then, an emoji pattern shows. Pictures aren't part of the skills, so there are no per-ingredient pictures.
- **Access: owner login + self-resetting demo + share links.** Everything is private; a recipe can get a public read-only link (`/r/<code>`).
- **Photos**: real photos, resized to ≤ 1000 px WebP and stored **in the database** (Render's free disk is wiped on restart), shown in a kawaii frame.
- **Discover: ready recipes from TheMealDB** to search, follow right away, and save to my recipes.
- The owner has a limited network, so API calls happen on the server and pictures are small.

### TheMealDB (checked on 2026-10-28)
The free key `1` is allowed "during development of your app or for educational use"; only app-store releases need a supporter key.
It has a **Filipino** area (Bistek, Caldereta, Mechado, Tortang Talong, Eggplant Adobo…), filters by **one** ingredient per call
(so several ingredients = several calls, with the ids intersected in Python), names some ingredients the British way (eggplant = "aubergine",
which our alias table bridges), and asks for the credit "Recipe data and imagery: TheMealDB".

## Stack

- Python 3.13, Flask 3, Jinja templates with server-rendered forms. Every page works without JavaScript; `app.js` adds row editing, cook mode (+ Wake Lock), the theme switch and shopping-list ticks.
- **SQLAlchemy 2.0** (`Mapped[...]`, one session per request) + **Alembic**. SQLite locally and in tests; **Neon Postgres** live (`DATABASE_URL`).
- **Pillow** for photos and the background tile. TheMealDB through `urllib` (no new library).
- Tests: pytest (never online). Deploy: Render (Singapore) + Neon (Singapore). Local port **5003**.

## Data model

```
users ─┬─< recipes ─┬─< recipe_ingredients >── ingredients ─< ingredient_aliases
       │            ├─< steps
       │            ├── photos (0 or 1)
       │            └─< recipe_tags >── tags
       ├─< tags
       └─< plan_entries >── recipes
```

| Table | Key columns | Notes |
|---|---|---|
| `users` | id, username UNIQUE, password_hash, is_demo, demo_reset_at, failed_logins, locked_until | As in Ang Gastos! |
| `recipes` | id, user_id, title, description, servings (1–100), prep/cook minutes, source_url, notes, is_favorite, **source** (`own`/`themealdb`), **external_id**, **share_code** UNIQUE, created/updated_at; UNIQUE(user_id, source, external_id) | |
| `ingredients` | id, name UNIQUE (normalized), kind, is_seeded | The **shared catalog** |
| `ingredient_aliases` | id, ingredient_id, alias UNIQUE | `bawang` → garlic, `aubergine` → eggplant |
| `recipe_ingredients` | id, recipe_id, ingredient_id (RESTRICT), position, amount, amount_max, unit, note, is_optional, section | The **association object** |
| `steps` | id, recipe_id, position, text | `ordering_list` |
| `tags` | id, user_id, name; UNIQUE(user_id, name) | |
| `recipe_tags` | recipe_id, tag_id (both the key) | The **plain association table** |
| `photos` | id, recipe_id UNIQUE, data (deferred), mime, width, height, size | |
| `plan_entries` | id, user_id, recipe_id, day, meal (CHECK), servings | |

Modeling decisions:
- **Two many-to-many patterns side by side:** Recipe ↔ Tag uses `secondary=`; Recipe ↔ Ingredient is an association object because the link has its own data.
- **The same ingredient may be in a recipe twice** (garlic in the marinade and the sauce); search counts `DISTINCT`.
- **Amounts are numbers** (1.5, not "1 1/2"), so they can be scaled and added up; "2–3" uses `amount_max`; no amount = "to taste". Units are a fixed list.
- **The catalog is shared, tags are private.** Autocomplete and ingredient pages only show starter ingredients + your own. Merging moves only your lines.
- **Deleting** a recipe cascades to its lines, steps, tag links, photo and plan entries. A used ingredient can't be deleted (RESTRICT), only merged.

## Search (`search.py`)

| Mode | SQL idea |
|---|---|
| **All** | `GROUP BY recipe HAVING COUNT(DISTINCT ingredient_id) = n` |
| **Any** | the same, `ORDER BY` the match count |
| **What I can cook** | `COUNT(DISTINCT CASE WHEN … NOT IN (yours) AND NOT optional AND NOT staple …) <= N` |
| **Without** | `NOT EXISTS` via `~Recipe.ingredients.any(...)` |
| Text, tags (every one), time, favorites | `ilike` (escaped), `.any()` per tag, `COALESCE` sums |

**Staples** (water, salt, oil, pepper) never count as missing when "I always have…" is ticked (on by default).
Found in testing: without it, "what can I cook" found almost nothing, because real recipes list water, salt and oil.
Results load with `selectinload` (a test counts the queries: no N+1).

## Stages (all ✅, one commit each, one PR)

1. ✅ **Setup, data model, migrations, login, theme**: `.venv`, all models, the first Alembic revision, `upgrade-db`, login/logout/CSRF/demo/lock-out, the kawaii theme (tokens for light + dark, toggle, puffy CSS, fonts, emoji background, logo), `/styleguide`, AGENTS.md/CLAUDE.md.
2. ✅ **Recipes**: `quantities.py`, `paste.py`, the starter catalog with aliases, the add/edit form (dynamic rows; "more rows" and "paste" also work without JS), the recipe page with the servings scaler.
3. ✅ **Search, tags, ingredients page**: every mode above, tags (rename = merge), ingredient counts and merge.
4. ✅ **Photos, demo data, cook mode, share links**: Pillow uploads, kawaii photo frame, 20 Filipino demo recipes + a week's plan, favorites, cook mode, print, JSON export, `/r/<code>`.
5. ✅ **Discover (TheMealDB)**: `mealdb.py`, follow + save once, alias bridging, fixtures, credit, CSP.
6. ✅ **Meal plan + shopping list**: week grid, totals per shelf with unit families combined.
7. ✅ **Polish and go-live prep**: icons, contrast check (all ≥ 4.5:1), security headers + CSP, `/healthz`, `render.yaml`, README (A1 English) + screenshots.

## After the PR (the owner's steps)

- **Go live:** make the Neon project (Singapore) and the Render Blueprint `sangkap`, then `create-user` against Neon. Steps in the README.
- **Background tile:** make one picture from `docs/ART_PROMPTS.md`, run `docs/make_background.py`, open a small PR.

## Verification

- `.venv\Scripts\python -m pytest`: quantities, paste, catalog, validation, photos, both many-to-many patterns and cascades,
  migrations = models, every search mode with exact results, query count, privacy (404 for others' recipes, tags, plan entries,
  ingredients and photos), share links, TheMealDB mapping + Discover (offline fixtures), shopping totals, demo limits.
- Manual: `flask --app sangkap run --debug --port 5003`, light/dark, phone width, cook mode; screenshots with `docs/take_screenshots.py`.

## After launch

- **UI/UX cleanup (PR #2, 2026-10-29):** decorative emoji removed (kept only for recipe pictures, empty-state illustrations and the ♥ sticker), wording and capitalization checked, the header on one row with the tabs lined up with the logo, the star after "Sangkap" removed, a tidy filter row on My recipes ("Manage tags" moved to Settings; filters apply on change), aligned forms and cards, sliding steps in cook mode (with swipe), a two-column shopping list, and the footer kept at the bottom.

- **Photo-only pictures (PR #3, 2026-10-29):** the emoji stand-in pictures repeated across recipes (every dessert had the same flan), so a recipe without a photo now gets a compact card with a candy-coloured strip, and the recipe page skips the picture. The emoji data was removed from the catalog.

- **Clearer cards and tabs (PR #4, 2026-10-29):** recipe cards lead with the name and a two-line description; time, servings and tags sit in one quiet footer. The tabs "Search" and "Discover" looked alike, so they are now **"What can I cook?"** (your own recipes, by ingredient) and **"Recipe ideas"** (new recipes from TheMealDB); the code and web addresses keep the old names (`search`, `discover`). The username left the header (it's the Log out button's tooltip) so the tabs fit on one row down to 1120px.

- **One place for each search (PR #5, 2026-10-29):** the separate search page is gone. **"What can I cook?"** is now the Ingredients tab, drawn as a **fridge** (meat, seafood, dairy shelves + a crisper drawer for produce) and a wooden **pantry** (pantry, spices, other): tap what you have, press Find recipes (default: missing 1 ingredient at most; water, salt, oil and pepper always count as had). **My recipes** got a search-by-name box in its filter row. Removed: the most-used-ingredient chips, the autocomplete list, the tag checkbox list, and the Without / Keywords / Total time / staples fields. The ingredient counts moved to Settings → Manage ingredients; old `/search` links redirect.

- **Meal plan redesign (PR #6, 2026-10-29):** the background pattern is now a soft texture everywhere (14% light / 10% dark, was 40% / 25%). The meal plan has one header row (title, a white pill week picker with Today, Shopping list), day columns with the date above a faint grey box that ends after its meals, solid white meal cards (a coloured meal pill, a dark bold title, small grey servings, a ⋯ menu with Open recipe / Remove instead of an ✕), and a dashed "+ Add a meal" button. Today is a pink label with a dot.

- **Settings and wording (PR #7, 2026-10-29):** Settings is one centred column with two cards (Your recipe box; Account). Every row has its name and description on the left and a same-width button on the right (full width under the text on phones), and the password form sits under its heading. A capitalization check over every page's headings, buttons, labels and titles led to: "Logged in as" (matching Log in / Log out), the error page's tab title matching its heading, the pantry shelf renamed "Dry goods & sauces" (it was "Pantry" inside the Pantry), and a clearer hidden label for the Match menu.

- **Sidebar navigation (PR #8, 2026-10-29):** like Gawi, the menu moved from the top bar to a sidebar on the left (logo, menu items with icons, then the username, light/dark switch and Log out at the bottom), with a ☰ menu on phones. The demo banner became a note under the username. Page layouts now use container queries, so they fit the space beside the sidebar. The login page matches Gawi too: a candy welcome panel on the left (big logo, "Kain na!") and one login card on the right with "or" and a big Try the demo button. And like Gawi, Sangkap is installable on a phone: a web manifest, a service worker (with a "You're offline" page), an Install app button in the sidebar and in Settings (shown only when the browser can install), and the iPhone steps in Settings.

- **Fill wide screens (PR #9, 2026-10-29):** pages used to stop at 1180px, leaving big empty margins on wide monitors. Now they fill the space beside the sidebar (up to 110rem), and the text grows on big screens (17px at 1600px, 18px at 1920px, 19px at 2300px wide), so everything stays readable. Settings and cook mode keep a comfortable reading width.

## Ideas for later

- Import a recipe from any web page (schema.org `Recipe` JSON-LD).
- Ratings and a "cooked on" history.
- Nutrition or cost per serving.
