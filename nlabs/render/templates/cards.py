# render/templates/cards.py — text cards in the tool's OWN design (never screenshots, S2):
# title, chapter, quote_card (typewriter), statement_card, post_card (recreated X post),
# list, stamp, names, doc, calendar, comment_prompt, subscribe, recap, endscreen.
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from ...constants import W, H, FPS
from .. import gfx
from .footage import bg_layer
from ..media import load_image


def _base(sh, i, ctx, dim=0.42):
    bg = bg_layer(sh, i, ctx, dim)
    if bg is not None:
        return Image.fromarray(bg)
    img = gfx.gradient_bg(ctx.c("bg"), ctx.c("panel"))
    return img


def title(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.45)
    d = ImageDraw.Draw(img)
    data = sh.get("data", {})
    a = gfx.ease_out(t / 0.6)
    f, lines = gfx.fit_font(data.get("title", "").upper(), "display", 1500, 420, 130)
    y = 540 - len(lines) * f.size * 0.6 + (1 - a) * 40
    for ln in lines:
        gfx.draw_text(d, (W / 2, y), ln, f, ctx.c("text"), stroke=2, anchor="mm")
        y += f.size * 1.15
    d.rectangle((W / 2 - 220 * a, y + 10, W / 2 + 220 * a, y + 22), fill=ctx.c("accent"))
    return gfx.to_np(img)


def chapter(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.4)
    d = ImageDraw.Draw(img)
    data = sh.get("data", {})
    a = gfx.ease_out(t / 0.45)
    x = 160 - (1 - a) * 120
    gfx.draw_text(d, (x, 380), f"CHAPTER {data.get('n', '')}", gfx.font("display", 56), ctx.c("accent"))
    f, lines = gfx.fit_font(str(data.get("title", "")).upper(), "display", 1500, 360, 120)
    y = 470
    for ln in lines:
        gfx.draw_text(d, (x, y), ln, f, ctx.c("text"), stroke=2)
        y += f.size * 1.12
    d.rectangle((x, 450, x + 300 * a, 460), fill=ctx.c("accent"))
    return gfx.to_np(img)


def _card_layout(sh, i, ctx):
    """If the card has real media, show it unblurred on the left 44 % (split-screen → footage)."""
    if sh.get("bg"):
        base = bg_layer(sh, i, ctx, 1.0)
        img = Image.fromarray(gfx.darken(gfx.blur(base), 0.35))
        left = gfx.fit_cover(base, 820, 1080)
        img.paste(Image.fromarray(np.ascontiguousarray(left)), (0, 0))
        return img, (900, 140, 1820, 940)
    return gfx.gradient_bg(ctx.c("bg"), ctx.c("panel")), (260, 160, 1660, 920)


def _highlight_lines(d, lines, f, x, y, ctx, key, n_chars=None):
    shown = 0
    for ln in lines:
        if n_chars is not None:
            if shown >= n_chars:
                break
            ln_draw = ln[: max(0, n_chars - shown)]
        else:
            ln_draw = ln
        shown += len(ln) + 1
        col = ctx.c("accent") if key and key.lower() in ln.lower() else ctx.c("text")
        gfx.draw_text(d, (x, y), ln_draw, f, col)
        y += f.size * 1.3
    return y


def post_card(sh, i, ctx):
    t = i / FPS
    img, box = _card_layout(sh, i, ctx)
    d = ImageDraw.Draw(img)
    data = sh.get("data", {})
    a = gfx.ease_out(t / 0.4)
    x0, y0, x1, y1 = box
    y0 += int((1 - a) * 60)
    gfx.shadow_box(img, (x0, y0, x1, y1), 28)
    gfx.panel(d, (x0, y0, x1, y1), (255, 255, 255), 28)
    # avatar initials (no logo images), name, verified mark, handle
    d.ellipse((x0 + 44, y0 + 44, x0 + 140, y0 + 140), fill=ctx.c("panel"))
    ini = "".join(p[0] for p in (data.get("author") or data.get("handle", "?")).split()[:2]).upper()
    gfx.draw_text(d, (x0 + 92, y0 + 92), ini, gfx.font("display", 40), (255, 255, 255), anchor="mm")
    name = data.get("author") or data.get("handle", "")
    nf = gfx.font("display", 40)
    gfx.draw_text(d, (x0 + 166, y0 + 58), name, nf, (15, 20, 25))
    if data.get("verified"):
        vx = x0 + 176 + gfx.text_w(name, nf)
        d.ellipse((vx, y0 + 62, vx + 36, y0 + 98), fill=(29, 155, 240))
        gfx.draw_text(d, (vx + 18, y0 + 80), "✓", gfx.font("fallback", 26), (255, 255, 255), anchor="mm")
    gfx.draw_text(d, (x0 + 166, y0 + 106), "@" + data.get("handle", ""), gfx.font("body", 30), (83, 100, 113))
    f, lines = gfx.fit_font(data.get("text", ""), "body", x1 - x0 - 100, y1 - y0 - 300, 52, 26)
    y = y0 + 190
    for ln in lines:
        gfx.draw_text(d, (x0 + 50, y), ln, f, (15, 20, 25))
        y += f.size * 1.3
    gfx.draw_text(d, (x0 + 50, y1 - 70), data.get("date", ""), gfx.font("body", 28), (83, 100, 113))
    gfx.draw_text(d, (x1 - 40, y1 + 36), data.get("source_line", ""), gfx.font("body", 26), ctx.c("muted"), anchor="ra")
    return gfx.to_np(img)


def statement_card(sh, i, ctx):
    t = i / FPS
    img, box = _card_layout(sh, i, ctx)
    d = ImageDraw.Draw(img)
    data = sh.get("data", {})
    x0, y0, x1, y1 = box
    gfx.panel(d, (x0, y0, x1, y1), ctx.c("panel"), 24, outline=ctx.c("accent"), width=4)
    gfx.draw_text(d, (x0 + 50, y0 + 40), "OFFICIAL STATEMENT", gfx.font("display", 40), ctx.c("accent"))
    if data.get("parts", 1) > 1:
        gfx.draw_text(d, (x1 - 50, y0 + 46), f"{data.get('part')}/{data.get('parts')}", gfx.font("body", 32),
                      ctx.c("muted"), anchor="ra")
    f, lines = gfx.fit_font("“" + data.get("text", "") + "”", "serif", x1 - x0 - 100, y1 - y0 - 240, 58, 26)
    n = int(len(data.get("text", "")) * min(1.0, t / max(0.8, min(3.0, sh["dur"] * 0.5)))) + 2
    _highlight_lines(d, lines, f, x0 + 50, y0 + 120, ctx, data.get("highlight"), n)
    gfx.draw_text(d, (x0 + 50, y1 - 70), "— " + (data.get("speaker") or ""), gfx.font("body", 34), ctx.c("text"))
    gfx.draw_text(d, (x1 - 40, y1 + 30), data.get("source_line", ""), gfx.font("body", 26), ctx.c("muted"), anchor="ra")
    return gfx.to_np(img)


def quote_card(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.35)
    d = ImageDraw.Draw(img)
    data = sh.get("data", {})
    text = data.get("text", "")
    n = int(len(text) * min(1.0, t / max(0.8, sh["dur"] * 0.6)))
    f, lines = gfx.fit_font("“" + text + "”", "serif", 1400, 600, 72)
    _highlight_lines(d, lines, f, 260, 260, ctx, data.get("highlight"), n + 1)
    gfx.draw_text(d, (260, 900), "— " + data.get("speaker", ""), gfx.font("body", 40), ctx.c("accent"))
    return gfx.to_np(img)


def list_card(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.35)
    d = ImageDraw.Draw(img)
    items = sh.get("data", {}).get("items", [])
    y = 540 - len(items) * 70
    for k, it in enumerate(items):
        a = gfx.ease_out((t - k * 0.25) / 0.35)
        if a <= 0:
            continue
        x = 300 - (1 - a) * 80
        d.rectangle((x - 40, y + 18, x - 16, y + 42), fill=ctx.c("accent"))
        gfx.draw_text(d, (x, y), str(it), gfx.font("display", 64), ctx.c("text"))
        y += 140
    return gfx.to_np(img)


STAMP_COLORS = {"CONFIRMED": "ok", "REPORTED": "info", "ALLEGED": "alert", "DENIED": "alert",
                "FACT CHECK": "accent", "HYPOTHETICAL": "accent", "ESTIMATE": "accent"}


def draw_stamp(img: Image.Image, label: str, t: float, ctx):
    """Rotated rubber-stamp overlay (used on top of footage too)."""
    a = gfx.ease_out(t / 0.25)
    if a <= 0:
        return img
    col = ctx.c(STAMP_COLORS.get(label, "accent"))
    f = gfx.font("display", 74)
    tw = int(gfx.text_w(label, f)) + 80
    st = Image.new("RGBA", (tw, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(st)
    d.rounded_rectangle((4, 4, tw - 4, 146), 14, outline=col + (255,), width=10)
    gfx.draw_text(d, (tw / 2, 77), label, f, col + (255,), anchor="mm")
    s = 1.6 - 0.6 * a
    st = st.resize((int(tw * s), int(150 * s))).rotate(-8, expand=True)
    img.paste(st, (W - st.width - 120, 110), st)
    return img


def stamp(sh, i, ctx):
    img = _base(sh, i, ctx, 0.4)
    return gfx.to_np(draw_stamp(img, sh.get("data", {}).get("label", "FACT CHECK"), i / FPS, ctx))


def names(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.35)
    d = ImageDraw.Draw(img)
    people = sh.get("data", {}).get("people", [])[:4]
    n = max(len(people), 1)
    cw = 360
    gap = (W - n * cw) // (n + 1)
    for k, p in enumerate(people):
        a = gfx.ease_out((t - k * 0.2) / 0.4)
        x = gap + k * (cw + gap)
        y = 300 + (1 - a) * 60
        gfx.panel(d, (x, y, x + cw, y + 480), ctx.c("panel"), 20)
        if p.get("photo"):
            ph = gfx.fit_cover(load_image(p["photo"]), cw - 40, 300)
            img.paste(Image.fromarray(np.ascontiguousarray(ph)), (x + 20, int(y + 20)))
        else:
            d.ellipse((x + 90, y + 40, x + 270, y + 220), fill=ctx.c("bg"))
            ini = "".join(w[0] for w in p.get("name", "?").split()[:2]).upper()
            gfx.draw_text(d, (x + 180, y + 130), ini, gfx.font("display", 70), ctx.c("accent"), anchor="mm")
        gfx.draw_text(d, (x + cw / 2, y + 360), p.get("name", ""), gfx.font("display", 38), ctx.c("text"), anchor="mm")
        gfx.draw_text(d, (x + cw / 2, y + 420), p.get("role", ""), gfx.font("body", 28), ctx.c("muted"), anchor="mm")
    return gfx.to_np(img)


def doc(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.35)
    d = ImageDraw.Draw(img)
    data = sh.get("data", {})
    y0 = 140 + (1 - gfx.ease_out(t / 0.5)) * 80
    gfx.shadow_box(img, (560, y0, 1360, y0 + 900), 6)
    d.rectangle((560, y0, 1360, y0 + 900), fill=(248, 246, 240))
    gfx.draw_text(d, (620, y0 + 60), data.get("heading", "DOCUMENT").upper(), gfx.font("display", 40), (30, 30, 30))
    y = y0 + 150
    for ln in gfx.wrap(data.get("text", ""), gfx.font("serif", 30), 680)[:16]:
        gfx.draw_text(d, (620, y), ln, gfx.font("serif", 30), (50, 50, 50))
        y += 44
    if data.get("highlight"):
        d.rectangle((610, y0 + 140, 1310, y0 + 190), outline=ctx.c("accent"), width=4)
    return gfx.to_np(img)


def calendar(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.35)
    d = ImageDraw.Draw(img)
    data = sh.get("data", {})
    a = gfx.ease_out(t / 0.5)
    gfx.panel(d, (710, 250, 1210, 800), (255, 255, 255), 30)
    d.rounded_rectangle((710, 250, 1210, 400), 30, fill=ctx.c("alert"))
    d.rectangle((710, 350, 1210, 400), fill=ctx.c("alert"))
    gfx.draw_text(d, (960, 325), data.get("month", "").upper(), gfx.font("display", 64), (255, 255, 255), anchor="mm")
    gfx.draw_text(d, (960, 600 - (1 - a) * 40), str(data.get("day", "")), gfx.font("display", 240), (20, 20, 20), anchor="mm")
    gfx.draw_text(d, (960, 880), data.get("label", ""), gfx.font("display", 52), ctx.c("text"), anchor="mm")
    return gfx.to_np(img)


def comment_prompt(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.35)
    d = ImageDraw.Draw(img)
    q = sh.get("data", {}).get("question", "")
    a = gfx.ease_out(t / 0.4)
    gfx.panel(d, (260, 300 + (1 - a) * 50, 1660, 780), ctx.c("panel"), 30, outline=ctx.c("info"), width=4)
    gfx.draw_text(d, (320, 350), "COMMENT BELOW", gfx.font("display", 44), ctx.c("info"))
    f, lines = gfx.fit_font(q, "display", 1260, 320, 72)
    y = 440
    for ln in lines:
        gfx.draw_text(d, (320, y), ln, f, ctx.c("text"))
        y += f.size * 1.2
    return gfx.to_np(img)


def subscribe(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.4)
    d = ImageDraw.Draw(img)
    a = gfx.ease_out(t / 0.4)
    w = int(560 * a)
    d.rounded_rectangle((960 - w // 2, 480, 960 + w // 2, 600), 60, fill=ctx.c("alert"))
    if a > 0.8:
        gfx.draw_text(d, (960, 540), "SUBSCRIBE", gfx.font("display", 64), (255, 255, 255), anchor="mm")
    return gfx.to_np(img)


def recap(sh, i, ctx):
    t = i / FPS
    img = _base(sh, i, ctx, 0.35)
    d = ImageDraw.Draw(img)
    gfx.draw_text(d, (200, 170), "SO FAR", gfx.font("display", 60), ctx.c("accent"))
    y = 300
    for k, it in enumerate(sh.get("data", {}).get("items", [])[:5]):
        if t < k * 0.4:
            break
        gfx.draw_text(d, (200, y), "→ " + it, gfx.font("body", 52), ctx.c("text"))
        y += 110
    return gfx.to_np(img)


def endscreen(sh, i, ctx):
    img = _base(sh, i, ctx, 0.35)
    d = ImageDraw.Draw(img)
    for x0 in (180, 1000):   # YouTube end-screen element slots
        d.rounded_rectangle((x0, 300, x0 + 740, 716), 18, outline=ctx.c("muted"), width=4)
    gfx.draw_text(d, (960, 150), sh.get("data", {}).get("text") or "WATCH NEXT", gfx.font("display", 80),
                  ctx.c("text"), anchor="mm")
    d.ellipse((860, 800, 1060, 1000), outline=ctx.c("accent"), width=6)
    return gfx.to_np(img)
