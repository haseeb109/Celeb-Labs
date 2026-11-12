# footage/hunt.py — Station 4 runner: queries → discover → tier/blocklist → subtitles →
# windows → scan → pool. Targets pool ≥ 3× needed footage seconds from ≥ 8 sources (F3)
# and writes footage_pool.json + pool stats for run_report.md. Resumable.
from __future__ import annotations

import json
import time

import numpy as np

from ..brain import run_pass, NeedsManual
from ..log import get_logger, progress
from ..util import read_json, write_json
from ..paths import ROOT
from . import discover, subtitles, soundbites, download, faces as facemod, pool as poolmod
from .blocklist import Blocklist
from .tiers import classify, load_tier_a

log = get_logger()


def fallback_queries(subject: str, ledger) -> list[str]:
    base = ["keynote", "interview", "speech", "press conference", "full interview", "on stage", "hearing",
            "commencement speech", "fireside chat", "Q&A", "announcement", "award", "panel", "podcast",
            "product launch", "visit"]
    q = [f"{subject} {b}" for b in base]
    for f in (ledger.facts if ledger else [])[:6]:
        words = [w for w in f["text"].split() if w[:1].isupper() and w.lower() not in subject.lower()][:3]
        if words:
            q.append(f"{subject} {' '.join(words)}")
    return q[:30]


def validate_fq(d):
    if not isinstance(d, dict) or not isinstance(d.get("queries"), list):
        return ['Expected {"queries":["...", ...]}']
    n = len(d["queries"])
    return [] if 15 <= n <= 30 else [f"need 15-30 queries, got {n}"]


def run_hunt(subject: str, ledger, script, cfg, rp, brain, need_seconds: float, reference_image=None,
             max_videos: int | None = None) -> dict:
    if rp.is_done("footage"):
        return read_json(rp.w("footage_pool.json"))
    bl = Blocklist()
    tier_a = load_tier_a(cfg.style_dir)
    official = read_json(ROOT / "official_accounts.json", {}) or {}
    official_ids = {i for e in official.values() if isinstance(e, dict) for i in e.get("youtube_channel_ids", [])}
    stats = {"queries": [], "candidates": 0, "rejected": [], "windows": 0, "windows_rejected": [],
             "need_seconds": round(need_seconds, 1), "errors": []}
    max_videos = max_videos or cfg.get("max_candidate_videos", 40)

    # 1. queries
    try:
        d = run_pass(brain, "footage_queries", [
            {"role": "system", "content": (cfg.prompt_path("footage.md").read_text(encoding="utf-8")
                                           if cfg.prompt_path("footage.md").exists() else "")},
            {"role": "user", "content": json.dumps({"subject": subject, "facts": [f["text"] for f in ledger.facts][:40]})}],
            validate_fq, 2, 2, 1500)
        queries = d["queries"]
    except NeedsManual:
        raise
    except Exception as e:
        log.warning(f"footage_queries failed ({e}); template queries")
        queries = fallback_queries(subject, ledger)
    stats["queries"] = queries
    keywords = list({w.strip(".,").lower() for q in queries for w in q.split() if len(w) > 3})

    # 2. discover
    entries, seen = [], set()
    for i, q in enumerate(queries):
        try:
            got = discover.search(cfg, q, cfg.get("yt_search_per_query", 15))
            ok, rej = discover.filter_entries(got, bl, seen)
            entries += ok
            stats["rejected"] += [{"id": e.get("id"), "channel": e.get("channel"), "reason": r} for e, r in rej]
        except Exception as e:
            stats["errors"].append(f"search '{q}': {type(e).__name__}: {str(e)[:120]}")
        progress(i + 1, len(queries), "yt search")
    for ch in tier_a.get("channels", []):
        if ch.get("id"):
            entries += discover.channel_search(cfg, ch["id"], subject, 8)
    uniq = {}
    for e in entries:
        if e.get("id") and e["id"] not in uniq:
            e["relevance"] = discover.relevance(e, keywords, subject)
            uniq[e["id"]] = e
    cands = sorted(uniq.values(), key=lambda e: e["relevance"], reverse=True)
    stats["candidates"] = len(cands)

    # 3. full metadata, tiers, subtitles → windows
    backend = facemod.get_backend(cfg.get("face_backend", "auto"))
    quotes = [q for q in ledger.quotes()] if ledger else []
    name_terms = [p.lower() for p in subject.split() if len(p) > 2]
    windows, sources = [], {}
    t0 = time.time()
    picked = cands[: max_videos]
    stats["candidate_list"] = [{"id": e["id"], "title": (e.get("title") or "")[:80], "channel": e.get("channel"),
                                "relevance": round(e["relevance"], 2)} for e in picked]
    bot_hits = 0
    for i, e in enumerate(picked):
        progress(i + 1, len(picked), "metadata", t0)
        try:
            info = discover.full_info(cfg, e["id"])
        except discover.BotCheck as bc:
            bot_hits += 1
            if bot_hits == 1 and cfg.get("yt_dlp_auto_update", True):
                download.ensure_fresh_ytdlp(force=False)       # fallback chain step 1: update yt-dlp
            if bot_hits >= 3:
                msg = ("YouTube bot check ('Sign in to confirm you're not a bot') on 3 videos in a row — this IP is "
                       "blocked. Run on a home/residential connection, or set cookies_file in config.json "
                       "(burner account cookies.txt). Stopping the metadata step.")
                log.error(msg)
                stats["errors"].append(msg)
                stats["bot_check"] = True
                break
            discover.polite_sleep(cfg)
            continue
        bot_hits = 0
        if not info:
            continue
        tier, lic = classify(info, tier_a, bl, official_ids)
        if tier == "BLOCKED":
            stats["rejected"].append({"id": e["id"], "channel": info.get("channel"), "reason": lic})
            continue
        words = []
        try:
            words = subtitles.fetch_words(info)
        except Exception:
            pass
        sbs = soundbites.find_soundbites(words, quotes, cfg.max_clip_s) if words and quotes else []
        mentions = subtitles.find_mentions(words, name_terms) if words else []
        dur = info.get("duration") or 0
        if dur and dur < 360:
            starts = [0.0]
            wl = min(dur, 40)
        else:
            starts = [max(0, m - 2) for m in mentions[:3]] + [s["start"] - 2 for s in sbs[:2]]
            if len(starts) < 2 and dur:
                starts += [dur * f for f in (0.08, 0.3, 0.55)][: 3 - len(starts)]
            wl = 20
        src = {"video_id": info["id"], "url": info.get("webpage_url") or f"https://youtu.be/{info['id']}",
               "title": info.get("title", ""), "channel": info.get("channel", ""), "channel_id": info.get("channel_id", ""),
               "tier": tier, "license": lic, "upload_date": info.get("upload_date", ""), "relevance": e["relevance"],
               "claims_subject": subject.lower() in (info.get("title", "") + info.get("description", "")).lower(),
               "official": info.get("channel_id") in official_ids, "soundbites": sbs}
        sources[info["id"]] = src
        for s in sorted(set(round(x, 1) for x in starts))[:4]:
            windows.append((info, src, s, wl))
        discover.polite_sleep(cfg) if i < len(picked) - 1 else None

    # 4. download windows and build the face reference
    ref = None
    if reference_image:
        import cv2
        im = cv2.imread(str(reference_image))
        ref = facemod.build_reference([im], backend) if im is not None else None
    downloaded = []
    t0 = time.time()
    for i, (info, src, s, wl) in enumerate(windows):
        progress(i + 1, len(windows), "windows", t0)
        p = download.download_window(info, s, wl, rp.footage_dir, cfg)
        if p:
            downloaded.append(src | {"path": str(p), "start": s, "length": wl})
        else:
            stats["windows_rejected"].append({"video_id": info["id"], "start": s, "reason": "download failed"})
        discover.polite_sleep(cfg) if i < len(windows) - 1 else None
    stats["windows"] = len(downloaded)
    if ref is None and backend.available:
        ref = auto_reference(downloaded, backend)
        stats["reference"] = "auto: dominant face in official/Tier A windows" if ref is not None else "none"
    else:
        stats["reference"] = "owner reference image" if ref is not None else "none"
    if ref is not None:
        np.save(rp.w("face_ref.npy"), ref)

    pool = build_pool(downloaded, cfg, ref, backend, bl, stats)
    write_json(rp.w("footage_pool.json"), pool)
    rp.mark_done("footage")
    return pool


def auto_reference(wins, backend):
    """Greedy face clustering over trusted windows; the largest cluster is the subject."""
    trusted = [w for w in wins if w["tier"] == "A" or w.get("official")] or [w for w in wins if w.get("claims_subject")]
    embs = []
    for w in trusted[:12]:
        for f in poolmod.read_frames(w["path"], [2.0, 8.0, 14.0]):
            for b, e in backend.faces(f):
                if e is not None and (b[2] - b[0]) > 0.06:
                    e = np.asarray(e, np.float32)
                    embs.append(e / (np.linalg.norm(e) + 1e-9))
    if len(embs) < 3:
        return None
    clusters: list[list] = []
    for e in embs:
        for c in clusters:
            if float(e @ (np.mean(c, axis=0))) > 0.5:
                c.append(e); break
        else:
            clusters.append([e])
    big = max(clusters, key=len)
    if len(big) < 3:
        return None
    m = np.mean(big, axis=0)
    return m / np.linalg.norm(m)


def build_pool(windows: list[dict], cfg, ref, backend, bl, stats: dict, use_ocr=True) -> dict:
    clips = []
    for i, w in enumerate(windows):
        cl, wlog = poolmod.scan_window(w, cfg, ref, backend, bl, use_ocr)
        if wlog.get("reject"):
            stats["windows_rejected"].append(wlog)
        for c in cl:
            for sb in w.get("soundbites", []):
                if w.get("start", 0) <= sb["start"] and sb["end"] <= w.get("start", 0) + w.get("length", 0):
                    c.setdefault("soundbite_candidates", []).append(sb)
        clips += cl
        progress(i + 1, len(windows), "scan")
    clips = poolmod.finalize(clips)
    total = sum(c["out"] - c["in"] for c in clips)
    srcs = {c["video_id"] for c in clips}
    stats.update(pool_seconds=round(total, 1), pool_clips=len(clips), pool_sources=len(srcs),
                 pool_ratio=round(total / max(stats.get("need_seconds", 1), 1), 2),
                 tiers={t: sum(1 for c in clips if c["tier"] == t) for t in "ABC"},
                 watermark_rejected=len([w for w in stats["windows_rejected"] if "scan" in str(w) or "OCR" in str(w)]),
                 face_backend=backend.name)
    stats["pool_ok"] = stats["pool_ratio"] >= cfg.pool_mult and len(srcs) >= cfg.min_sources
    if not stats["pool_ok"]:
        log.warning(f"F3: pool {total:.0f}s from {len(srcs)} sources (need {cfg.pool_mult}x "
                    f"{stats.get('need_seconds')}s from {cfg.min_sources}) — photos will fill; never breaking F2/F6/F7")
    return {"clips": clips, "stats": stats}
