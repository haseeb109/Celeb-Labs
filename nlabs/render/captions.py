# render/captions.py — word-by-word captions: chunks of ≤5 words, the current word in the
# accent color, thick stroke. Never covers a face: if the shot's face box reaches the
# lower third of the frame, captions move to the top.
from __future__ import annotations

from PIL import ImageDraw

from ..constants import W, H
from . import gfx


def chunks(words: list[dict], max_words: int = 5) -> list[list[dict]]:
    out, cur = [], []
    for w in words:
        cur.append(w)
        end_sent = w["w"].endswith((".", "?", "!", ","))
        if len(cur) >= max_words or end_sent:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def draw(img, t: float, chunk_list, ctx, size=62, stroke=5, active="accent", avoid_box=None):
    cur = None
    for ch in chunk_list:
        if ch[0]["start"] - 0.05 <= t <= ch[-1]["end"] + 0.25:
            cur = ch
    if not cur:
        return img
    d = ImageDraw.Draw(img)
    f = gfx.font("display", size)
    words = [w["w"].upper() for w in cur]
    space = gfx.text_w(" ", f)
    total = sum(gfx.text_w(w, f) for w in words) + space * (len(words) - 1)
    if total > W - 200:
        f = gfx.font("display", int(size * (W - 200) / total))
        space = gfx.text_w(" ", f)
        total = sum(gfx.text_w(w, f) for w in words) + space * (len(words) - 1)
    y = 930
    if avoid_box and avoid_box[3] > 0.72:
        y = 150
    x = (W - total) / 2
    for w, raw in zip(words, cur):
        col = ctx.c(active) if raw["start"] <= t <= raw["end"] + 0.05 else ctx.c("text")
        gfx.draw_text(d, (x, y), w, f, col, stroke=stroke, stroke_fill=(0, 0, 0), anchor="lm")
        x += gfx.text_w(w, f) + space
    return img
