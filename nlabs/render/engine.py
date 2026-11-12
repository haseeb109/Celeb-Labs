# render/engine.py — renders every segment independently (raw RGB → ffmpeg pipe) in
# parallel workers, resumable via a hash of each segment's spec. HARD ASSERT for Rule F2:
# no third-party footage shot may exceed 5.0 s — a forged plan cannot get past this.
from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ..constants import FPS, MAX_CLIP_SECONDS, LockedRuleError
from ..log import get_logger, progress
from ..util import sha1
from . import encode
from .captions import chunks

log = get_logger()


def assert_plan_rules(plan: dict, max_clip_s: float = MAX_CLIP_SECONDS):
    """F2 hard assert + basic integrity. Raised BEFORE any frame is rendered."""
    cap = min(max_clip_s, MAX_CLIP_SECONDS)
    for seg in plan["segments"]:
        tot = 0.0
        for sh in seg["shots"]:
            if sh.get("template") == "footage" and sh.get("is_third_party", True) and sh["dur"] > cap + 1e-6:
                raise LockedRuleError(f"F2 violated: shot {sh['shot_id']} ({sh.get('channel')}) is "
                                      f"{sh['dur']:.2f}s > {cap:.1f}s")
            if sh.get("bg", {}).get("kind") == "clip" and sh["dur"] > cap + 1e-6:
                raise LockedRuleError(f"F2 violated: background clip in {sh['shot_id']} is {sh['dur']:.2f}s")
            tot += sh["dur"]
        if abs(tot - seg["dur"]) > 1.5 / FPS:
            raise LockedRuleError(f"segment {seg['seg_id']}: shots {tot:.3f}s != segment {seg['dur']:.3f}s")


def seg_hash(seg: dict, style: str, extra: dict) -> str:
    return sha1(json.dumps(seg, sort_keys=True, default=str), style, json.dumps(extra, sort_keys=True))[:12]


def render_segment(args) -> str:
    seg, idx, out_path, style, overrides, glob = args
    from ..config import Config
    from .media import Ctx
    from .templates import for_style
    from .overlays import apply
    cfg = Config(style, overrides)
    tmpls = for_style(cfg.style_dir)
    ctx = Ctx(cfg)
    enc = glob["encoder"]
    tmp = Path(out_path).with_suffix(".part.mp4")
    p = subprocess.Popen(encode.raw_pipe_cmd(tmp, enc), stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    caps = chunks(seg.get("captions") or [], glob.get("cap_words", 5))
    g = dict(glob)
    g["t0"] = seg["start"]
    ch_titles = glob.get("chapter_titles", {})
    g["chapter_tag"] = ch_titles.get(str(seg.get("chapter")), "")
    total_frames = seg["frames"]
    f = 0
    try:
        for sh in seg["shots"]:
            n = int(round(sh["dur"] * FPS))
            fn = tmpls.get(sh["template"]) or tmpls["list"]
            for i in range(n):
                if f >= total_frames:
                    break
                frame = fn(sh, i, ctx)
                frame = apply(frame, sh, i / FPS, f / FPS, seg, ctx, caps, g)
                p.stdin.write(frame.tobytes())
                f += 1
        while f < total_frames:      # pad by repeating last frame (rounding)
            p.stdin.write(frame.tobytes())
            f += 1
        p.stdin.close()
        err = p.stderr.read().decode(errors="ignore")
        if p.wait() != 0:
            raise RuntimeError(f"encode failed for {seg['seg_id']}: {err[-500:]}")
    finally:
        ctx.close()
    tmp.replace(out_path)
    return out_path


def render_all(plan: dict, cfg, rp, only: set | None = None, rerender: set | None = None) -> list[Path]:
    assert_plan_rules(plan, cfg.max_clip_s)
    enc = encode.pick_encoder(cfg.get("encoder", "auto"))
    cap = cfg.style.get("captions", {})
    chapter_titles = {}
    for s in plan["segments"]:
        if s["kind"] == "chapter":
            chapter_titles[str(s.get("chapter"))] = f"CH {s.get('chapter')} · {str(s.get('text', '')).upper()[:34]}"
    glob = {"encoder": enc, "total": plan["runtime"], "captions_on": cap.get("on", True), "cap_words": cap.get("max_words", 5),
            "cap_size": cap.get("size", 62), "cap_stroke": cap.get("stroke", 5), "cap_active": cap.get("active_color", "accent"),
            "grain": bool(cfg.style.get("grain", False)), "chapter_titles": chapter_titles}
    jobs, files = [], []
    overrides = {k: v for k, v in cfg.raw.items() if k in ("parallel_workers", "encoder")}
    for idx, seg in enumerate(plan["segments"]):
        h = seg_hash(seg, cfg.style_name, {k: v for k, v in glob.items() if k != "encoder"} | {"enc": enc})
        out = rp.seg_dir / f"v{idx:03d}_{h}.mp4"
        for old in rp.seg_dir.glob(f"v{idx:03d}_*.mp4"):
            if old != out:
                old.unlink()
        if rerender and seg["seg_id"] in rerender and out.exists():
            out.unlink()
        files.append(out)
        if not out.exists():
            jobs.append((seg, idx, str(out), cfg.style_name, overrides, glob))
    log.info(f"render: {len(jobs)} of {len(files)} segments to render with {cfg.workers} workers ({enc})")
    t0 = time.time()
    if jobs:
        if cfg.workers <= 1:
            for k, j in enumerate(jobs):
                render_segment(j)
                progress(k + 1, len(jobs), "render", t0)
        else:
            with ProcessPoolExecutor(max_workers=cfg.workers) as ex:
                futs = [ex.submit(render_segment, j) for j in jobs]
                for k, fu in enumerate(as_completed(futs)):
                    fu.result()
                    progress(k + 1, len(jobs), "render", t0)
    return files
