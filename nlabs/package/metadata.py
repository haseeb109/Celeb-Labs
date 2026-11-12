# package/metadata.py — metadata.txt: 5 titles in 5 hook styles (≤70 chars), description with
# summary, chapters from the REAL timeline, recency stamp (L6), sources, footage/image/music
# credits, disclaimer for unproven allegations, 15 tags, pinned comment question.
from __future__ import annotations

import json

from ..brain import run_pass

STYLES = ["curiosity", "consequence", "number", "question", "contrarian"]


def ts(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def chapters(plan) -> list[str]:
    out = ["0:00 Intro"]
    for seg in plan["segments"]:
        if seg["kind"] == "chapter" and seg["start"] > 0:
            out.append(f"{ts(seg['start'])} {seg.get('text', '').strip()}")
    return out


def validate_titles(d):
    if not isinstance(d, dict) or not isinstance(d.get("titles"), list):
        return ['Expected {"titles":[{"style":"curiosity","text":"..."},...], "tags":[...], "summary":"...", "pinned_comment":"..."}']
    errs = []
    styles = [t.get("style") for t in d["titles"]]
    for s in STYLES:
        if s not in styles:
            errs.append(f"missing title style '{s}'")
    for t in d["titles"]:
        if len(t.get("text", "")) > 70:
            errs.append(f"title too long ({len(t['text'])}>70): {t['text']}")
    if len(d.get("tags", [])) < 15:
        errs.append("need 15 tags")
    return errs


def fallback_titles(subject, topic):
    t = [("curiosity", f"The Real Reason Behind {subject}'s Shock Exit"),
         ("consequence", f"{subject}'s Decision Just Changed Everything"),
         ("number", f"7 Days That Ended {subject}'s Reign"),
         ("question", f"What Really Happened to {subject}?"),
         ("contrarian", f"Everyone Is Wrong About {subject}")]
    return {"titles": [{"style": s, "text": x[:70]} for s, x in t], "summary": topic,
            "tags": [subject, topic][:2] + ["news", "explained", "breaking news", "business news", "ceo", "scandal",
                                            "timeline", "analysis", "documentary", "what happened", "latest",
                                            "update", "full story"], "pinned_comment": f"What do you think happens next for {subject}?"}


def build(script, ledger, plan, footage_rows, image_lines, music_credits, cfg, brain, rp, official):
    subject, topic = script.get("subject", ""), script.get("topic", "")
    try:
        d = run_pass(brain, "titles", [
            {"role": "system", "content": cfg.prompt_path("titles.md").read_text(encoding="utf-8")
             if cfg.prompt_path("titles.md").exists() else ""},
            {"role": "user", "content": json.dumps({"subject": subject, "topic": topic,
                                                    "facts": [f["text"] for f in ledger.facts if f["status"] == "confirmed"][:20]})}],
            validate_titles, 2, 2, 1500)
    except Exception:
        d = fallback_titles(subject, topic)
    alleged = any(f["status"] in ("alleged", "reported") for f in ledger.facts)
    srcs = []
    for f in ledger.facts:
        for s in f.get("sources", []):
            line = f"- {s.get('outlet', '')}: {s['url']}"
            if line not in srcs:
                srcs.append(line)
    fc = []
    for r in footage_rows:
        line = f"- {r['channel']} — {r['url']} ({'public domain' if r['tier'] == 'A' else r['license']})"
        if line not in fc:
            fc.append(line)
    cp = next((s for s in script["segments"] if s.get("retention") == "comment_prompt"), None)
    L = ["TITLES (pick one)"] + [f"  [{t['style']}] {t['text']}" for t in d["titles"]] + ["", "DESCRIPTION", "",
         d.get("summary", topic), "",
         f"Information current as of {ledger.researched_at} {ledger.tz}.", "", "CHAPTERS"] + chapters(plan)
    L += ["", "SOURCES"] + (srcs or ["- (see fact_ledger.json)"])
    L += ["", "FOOTAGE CREDITS (short excerpts used for news commentary; public-domain government footage marked)"] + fc
    L += ["", "IMAGE CREDITS"] + [x if x.startswith((" ", "Stills")) else f"- {x}" for x in image_lines if x.strip()]
    L += ["", "MUSIC"] + [f"- {m}" for m in music_credits]
    if alleged:
        L += ["", "DISCLAIMER: Allegations and reports described in this video are unproven unless stated as confirmed. "
              "Denials are included where they exist."]
    L += ["", "TAGS", ", ".join(d.get("tags", [])[:15]), "", "PINNED COMMENT",
          d.get("pinned_comment") or (cp.get("text") if cp else f"What do you think happens next for {subject}?")]
    rp.o("metadata.txt").write_text("\n".join(L), encoding="utf-8")
    return d
