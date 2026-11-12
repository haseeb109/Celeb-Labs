# render/templates/charts.py — motion graphics (count toward the ≤20 % animation cap, F1):
# counter, timeline, chart_line, bars. Data comes from the script's visual.graphic block
# (numbers must come from ledger facts; labels like ESTIMATE are drawn when flagged, L5).
from __future__ import annotations

from PIL import ImageDraw

from ...constants import W, H, FPS
from .. import gfx


def _bg(ctx):
    return gfx.gradient_bg(ctx.c("bg"), ctx.c("panel"))


def _label(d, data, ctx):
    gfx.draw_text(d, (140, 90), data.get("title", ""), gfx.font("display", 58), ctx.c("text"))
    if data.get("estimate") or data.get("hypothetical"):
        tag = "HYPOTHETICAL" if data.get("hypothetical") else "ESTIMATE"
        gfx.panel(d, (W - 520, 86, W - 140, 156), ctx.c("accent"), 10)
        gfx.draw_text(d, (W - 330, 121), tag, gfx.font("display", 40), ctx.c("bg"), anchor="mm")
    if data.get("source"):
        gfx.draw_text(d, (140, H - 90), "Source: " + data["source"], gfx.font("body", 28), ctx.c("muted"))


def counter(sh, i, ctx):
    data = sh.get("data", {})
    img = _bg(ctx)
    d = ImageDraw.Draw(img)
    p = gfx.ease_out(i / FPS / max(1.2, sh["dur"] * 0.5))
    v = data.get("from", 0) + (data.get("to", 0) - data.get("from", 0)) * p
    fmt = data.get("format", "{:,.0f}")
    s = data.get("prefix", "") + fmt.format(v) + data.get("suffix", "")
    gfx.draw_text(d, (W / 2, 520), s, gfx.font("display", 200), ctx.c("accent"), anchor="mm")
    gfx.draw_text(d, (W / 2, 700), data.get("label", ""), gfx.font("body", 54), ctx.c("text"), anchor="mm")
    _label(d, data, ctx)
    return gfx.to_np(img)


def timeline(sh, i, ctx):
    data = sh.get("data", {})
    img = _bg(ctx)
    d = ImageDraw.Draw(img)
    ev = data.get("events", [])[:6]
    p = gfx.ease_out(i / FPS / max(1.5, sh["dur"] * 0.6))
    x0, x1, y = 180, W - 180, 560
    d.rectangle((x0, y - 4, x0 + (x1 - x0) * p, y + 4), fill=ctx.c("muted"))
    for k, e in enumerate(ev):
        fx = k / max(len(ev) - 1, 1)
        if fx > p + 1e-6:
            break
        x = x0 + (x1 - x0) * fx
        d.ellipse((x - 18, y - 18, x + 18, y + 18), fill=ctx.c("accent"))
        up = k % 2 == 0
        gfx.draw_text(d, (x, y - 80 if up else y + 60), e.get("date", ""), gfx.font("display", 38), ctx.c("accent"), anchor="mm")
        for j, ln in enumerate(gfx.wrap(e.get("label", ""), gfx.font("body", 30), 300)[:3]):
            yy = (y - 150 - j * 38) if up else (y + 110 + j * 38)
            gfx.draw_text(d, (x, yy), ln, gfx.font("body", 30), ctx.c("text"), anchor="mm")
    _label(d, data, ctx)
    return gfx.to_np(img)


def chart_line(sh, i, ctx):
    data = sh.get("data", {})
    img = _bg(ctx)
    d = ImageDraw.Draw(img)
    pts = data.get("points", [])
    if len(pts) >= 2:
        vals = [float(p[1]) for p in pts]
        lo, hi = min(vals), max(vals)
        rng = (hi - lo) or 1
        x0, x1, y0, y1 = 200, W - 200, 250, H - 220
        for gy in range(5):
            yy = y0 + (y1 - y0) * gy / 4
            d.line((x0, yy, x1, yy), fill=(40, 52, 75), width=2)
        p = gfx.ease_in_out(i / FPS / max(1.5, sh["dur"] * 0.7))
        n = max(2, int(len(pts) * p + 1))
        xy = [(x0 + (x1 - x0) * k / (len(pts) - 1), y1 - (y1 - y0) * (v - lo) / rng) for k, v in enumerate(vals)][:n]
        d.line(xy, fill=ctx.c("accent"), width=8, joint="curve")
        lx, ly = xy[-1]
        d.ellipse((lx - 14, ly - 14, lx + 14, ly + 14), fill=ctx.c("accent"))
        gfx.draw_text(d, (lx, ly - 40), str(pts[n - 1][1]) + data.get("unit", ""), gfx.font("display", 44), ctx.c("text"), anchor="mm")
        for k in (0, len(pts) - 1):
            gfx.draw_text(d, (x0 + (x1 - x0) * k / (len(pts) - 1), y1 + 50), str(pts[k][0]), gfx.font("body", 30),
                          ctx.c("muted"), anchor="mm")
    _label(d, data, ctx)
    return gfx.to_np(img)


def bars(sh, i, ctx):
    data = sh.get("data", {})
    img = _bg(ctx)
    d = ImageDraw.Draw(img)
    items = data.get("items", [])[:6]
    mx = max([float(v) for _, v in items] or [1]) or 1
    for k, (lab, v) in enumerate(items):
        p = gfx.ease_out((i / FPS - k * 0.15) / 0.8)
        y = 260 + k * 120
        gfx.draw_text(d, (180, y + 40), str(lab), gfx.font("body", 38), ctx.c("text"), anchor="lm")
        w = (W - 900) * float(v) / mx * max(p, 0)
        d.rounded_rectangle((620, y + 10, 620 + max(w, 4), y + 70), 10, fill=ctx.c("accent" if k == 0 else "info"))
        if p > 0.3:
            gfx.draw_text(d, (640 + w, y + 40), f"{v}{data.get('unit', '')}", gfx.font("display", 38), ctx.c("text"), anchor="lm")
    _label(d, data, ctx)
    return gfx.to_np(img)
