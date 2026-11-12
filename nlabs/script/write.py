# script/write.py — Station 3 runner: outline → script → validate/repair → script.json/.txt.
# Length targeting uses chars/sec calibration; the brain adds/removes WHOLE segments.
# Resumable: skips when work/<run>/done/script exists.
from __future__ import annotations

import json

from ..brain import run_pass
from ..log import get_logger
from ..util import write_json, read_json
from .outline import run_outline
from .validate_script import validate_script, est_seconds
from .timing import chars_per_sec

log = get_logger()


def _prompt(cfg, name):
    p = cfg.prompt_path(name)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    ex = cfg.style_dir / "prompts" / "examples"
    if ex.exists():
        for f in sorted(ex.glob(f"{name.split('.')[0]}*")):
            text += f"\n\n### GOLD EXAMPLE ({f.name})\n" + f.read_text(encoding="utf-8")
    return text


def banned_list(cfg) -> list[str]:
    p = cfg.style_dir / "prompts" / "banned.txt"
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")] \
        if p.exists() else []


def run_script(topic, subject, ledger, official, cfg, rp, brain, minutes: float):
    if rp.is_done("script"):
        return read_json(rp.o("script.json"))
    target = minutes * 60
    v = cfg.style.get("voice", {})
    cps = chars_per_sec(v.get("voice_id", ""), v.get("speed", 1.0))
    pacing = cfg.style.get("pacing", {})
    outline = read_json(rp.w("outline.json"))
    if not outline:
        outline = run_outline(topic, subject, ledger, official, cfg, brain, minutes, _prompt(cfg, "outline.md"))
        write_json(rp.w("outline.json"), outline)

    def validator(d):
        return validate_script(d, ledger, official.get("cards", []), target, 0.03, cps, pacing,
                               banned_list(cfg), cfg.style.get("retention", {}))

    payload = {"topic": topic, "subject": subject, "target_seconds": target, "chars_per_second": cps,
               "target_characters": int(target * cps * 0.86), "outline": outline, "ledger": ledger.facts,
               "official_cards": official.get("cards", []), "retention": cfg.style.get("retention", {})}
    script = run_pass(brain, "script", [{"role": "system", "content": _prompt(cfg, "script.md")},
                                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                      validator, cfg.get("brain_attempts", 3), cfg.get("max_repair_rounds", 3), 16000, 0.5)
    script["subject"] = subject
    script["topic"] = topic
    script["est_seconds"] = round(sum(est_seconds(s, cps, pacing) for s in script["segments"]), 1)
    write_json(rp.o("script.json"), script)
    write_script_txt(script, rp.o("script.txt"))
    rp.mark_done("script")
    return script


def write_script_txt(script, path):
    L, ch = [], None
    for s in script["segments"]:
        if s["kind"] == "chapter":
            L += ["", f"== CHAPTER {s.get('chapter')}: {s.get('text', '')} ==", ""]
        elif s["kind"] in ("title", "endscreen"):
            L += [f"[{s['kind'].upper()}] {s.get('text', '')}", ""]
        elif s["kind"] in ("post", "statement", "soundbite"):
            L += [f"[{s['kind'].upper()} {','.join(s.get('fact_ids', []))}] {s.get('text', '')}", ""]
        else:
            L += [s.get("text", ""), ""]
    path.write_text("\n".join(L), encoding="utf-8")
