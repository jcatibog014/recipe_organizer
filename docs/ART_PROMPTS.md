# The kawaii background picture

Sangkap has one picture to make: a **background tile** of cute 3D ingredients.
It repeats behind every page as a soft texture: 14% strong (10% in dark mode).
Until you make it, the app shows a pattern of food emoji instead, so nothing is broken.

## 1. Make the picture

Use a free AI image tool: **ChatGPT**, **Gemini** or **Bing Image Creator**.
Copy this prompt:

> Seamless repeating pattern tile of cute 3D kawaii clay-toy ingredients: garlic, tomato, chili, onion,
> calamansi, egg, carrot, mushroom, shrimp, a small rice bowl. Glossy soft plastic, chubby rounded shapes,
> small shiny black eyes with white highlights, pink blush cheeks, happy faces. Bright candy colours
> (strawberry pink, mint, lemon yellow, sky blue). Soft studio light. Scattered with plenty of space
> between them, slightly rotated. Square image, transparent background, no text, no shadows on the background.

Tips:
- In ChatGPT, also say: **"Make the background transparent (PNG)."**
- Bing gives a JPG on white. That is OK: the script removes a plain white background.
- If the faces look scary or messy, ask again: *"cuter, simpler, bigger eyes, more space between the items."*
- Space between the items is important: the cards sit on top, and a busy picture looks noisy.

## 2. Save it

Save it as:

```
C:\Users\USER\Documents\Workspace\recipe_organizer\docs\art_src\background.png
```

(`.jpg` and `.webp` also work.) The `art_src` folder is not uploaded to GitHub.

## 3. Turn it into the tile

```
.venv\Scripts\python docs\make_background.py
```

This makes `sangkap/static/art/pattern.webp` (about 30–60 KB). Restart the app to see it.
Then commit `pattern.webp` in a small pull request.

☐ Picture made  ☐ Saved in `docs/art_src/`  ☐ Script run  ☐ Looks good in light and dark  ☐ PR merged
