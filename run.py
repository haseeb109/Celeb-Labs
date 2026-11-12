#!/usr/bin/env python3
# run.py — command-line entry for N Labs · UMF News Factory.
# Example: python run.py "Jensen Huang resigns as Nvidia CEO" --style news_explainer --minutes 20
# See README.md for every flag; the launcher menus (N Labs.bat / .command) call this file.
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run.py", description="N Labs · UMF News Factory")
    ap.add_argument("topic", nargs="?", help="topic or news story in plain text")
    ap.add_argument("--style", default="news_explainer")
    ap.add_argument("--minutes", type=float, default=None)
    ap.add_argument("--stage", choices=["research", "script", "plan", "render", "all"], default="all")
    ap.add_argument("--brain", choices=["deepseek", "hive", "anthropic", "openai", "manual", "mock"], default=None)
    ap.add_argument("--auto", action="store_true", help="skip approval gates (locked rules still apply)")
    ap.add_argument("--confirm-tts", action="store_true", help="allow more than 5,000 TTS characters")
    ap.add_argument("--resume", metavar="RUN_ID")
    ap.add_argument("--approve", action="append", choices=["script", "plan"], help="approve a gate for --resume")
    ap.add_argument("--only-render", action="store_true")
    ap.add_argument("--rerender-seg", action="append", default=[], metavar="SEG_ID")
    ap.add_argument("--reference-image", metavar="JPG")
    ap.add_argument("--posts", metavar="posts_manual.json")
    ap.add_argument("--subject", help="override the detected subject name")
    ap.add_argument("--footage-preview", action="store_true", help="run only the footage hunt for the topic")
    ap.add_argument("--max-videos", type=int, default=None, help="cap candidate videos (footage hunt)")
    ap.add_argument("--list-styles", action="store_true")
    ap.add_argument("--list-runs", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--update-tools", action="store_true", help="update yt-dlp now")
    ap.add_argument("--init-keys", action="store_true", help="create empty key files in ~/.config/umf/")
    a = ap.parse_args(argv)

    if a.list_styles:
        from nlabs.config import list_styles
        print("\n".join(list_styles()))
        return 0
    if a.list_runs:
        for p in sorted((ROOT / "work").glob("*/run.json")):
            r = json.loads((p.parent / "result.json").read_text()) if (p.parent / "result.json").exists() else {}
            print(f"{p.parent.name:<60} {r.get('status', '?')}")
        return 0
    if a.selftest:
        cmd = [sys.executable, str(ROOT / "tests" / "run_tests.py")] + (["--quick"] if a.quick else [])
        return subprocess.call(cmd)
    if a.update_tools:
        from nlabs.footage.download import ensure_fresh_ytdlp
        print("yt-dlp:", ensure_fresh_ytdlp(force=True))
        return 0
    if a.init_keys:
        from nlabs.config import ensure_key_templates
        from nlabs.paths import KEY_DIR
        ensure_key_templates()
        print(f"Key files ready in {KEY_DIR} (edit them; never put keys in the project folder)")
        return 0
    if not a.topic and not a.resume:
        ap.error("give a topic, or --resume RUN_ID")
    if a.footage_preview:
        from nlabs.pipeline import footage_preview
        r = footage_preview(a.topic, a.subject, a.style, a.minutes or 20, a.brain, a.reference_image, a.max_videos)
        print(json.dumps(r, indent=2))
        return 0
    from nlabs.pipeline import run
    overrides = {}
    r = run(a.topic, a.style, a.minutes, a.stage, a.brain, a.auto, a.confirm_tts, a.resume, a.only_render,
            a.rerender_seg, a.reference_image, a.posts, a.subject, a.approve, overrides)
    print(json.dumps({k: v for k, v in r.items() if k != "message"}, indent=2))
    return 0 if r["status"] in ("done", "awaiting_approval") or r["status"].startswith("stopped") else 2


if __name__ == "__main__":
    sys.exit(main())
