# render/templates/ — registry of all templates: name → function(shot, frame_index, ctx) → RGB frame.
# Styles can override any template by placing a module in styles/<style>/templates/<name>.py
# that defines `render(shot, i, ctx)`.
import importlib.util
from pathlib import Path

from . import footage as _f, cards as _c, charts as _g

TEMPLATES = {
    "footage": _f.footage, "photo_card": _f.photo_card, "kb_image": _f.kb_image,
    "title": _c.title, "chapter": _c.chapter, "quote_card": _c.quote_card, "statement_card": _c.statement_card,
    "post_card": _c.post_card, "list": _c.list_card, "stamp": _c.stamp, "names": _c.names, "doc": _c.doc,
    "calendar": _c.calendar, "comment_prompt": _c.comment_prompt, "subscribe": _c.subscribe, "recap": _c.recap,
    "endscreen": _c.endscreen, "counter": _g.counter, "timeline": _g.timeline, "chart_line": _g.chart_line,
    "bars": _g.bars,
}
TEMPLATES["split"] = lambda sh, i, ctx: _f.footage({**sh, "treatment": "split"}, i, ctx)
TEMPLATES["lower_third"] = None   # overlay, see render/overlays.py


def for_style(style_dir: Path) -> dict:
    out = dict(TEMPLATES)
    d = Path(style_dir) / "templates"
    for p in d.glob("*.py") if d.exists() else []:
        spec = importlib.util.spec_from_file_location(f"style_tmpl_{p.stem}", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        if hasattr(m, "render"):
            out[p.stem] = m.render
    return out
