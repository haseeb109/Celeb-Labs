# Adding a style

The engine is style-agnostic. Everything channel/format-specific lives in `styles/<name>/`.

1. Copy the folder: `styles/news_explainer` → `styles/my_style`.
2. Edit `styles/my_style/style.json`:
   - `palette` (bg, panel, accent, alert, ok, info, text, muted), `fonts`, `captions`, `voice` (ai33 `voice_id`, `speed`),
     `music.mood`/`duck_db`, `pacing`, `retention`, `chapters`, `target_minutes`, `narrative`.
   - `ratios` can only be **stricter** than the locked rules (≥0.65 footage, ≤0.20 animation, ≤0.15 text).
3. Edit prompts in `styles/my_style/prompts/` (`research.md`, `extract_facts.md`, `outline.md`, `script.md`,
   `titles.md`, `footage.md`, `banned.txt`) and the gold examples in `prompts/examples/`
   (better examples = better results from cheaper brains).
4. Optional: override any render template by adding `styles/my_style/templates/<template_name>.py` with
   `def render(shot, i, ctx): ...` returning a 1920×1080 RGB numpy frame (see `nlabs/render/templates/cards.py`).
5. Optional: fonts in `styles/my_style/assets/fonts/` (open-license only; list them in `FONT_LICENSES.txt`).
6. Optional: `sources_tierA.json` — public-domain channels for this niche.
7. Check it: `python run.py --list-styles`, then `python run.py --selftest --quick`.
8. Use it: `python run.py "topic" --style my_style` (the launcher asks for the style too).
