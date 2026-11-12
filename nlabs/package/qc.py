# package/qc.py — qc.json: re-measures every locked rule on the FINAL output: runtime, F1 ratios,
# max clip length (≤5.0), per-source caps, blocklist hits (must be 0), watermark rejects,
# face stats, loudness, size, TTS chars, API cost → overall OK / CHECK.
from __future__ import annotations

from ..constants import MAX_CLIP_SECONDS
from ..edit import ratios
from ..footage.blocklist import Blocklist
from ..footage.select import check_caps
from ..util import duration, probe, write_json


def run(plan, video, mix, cfg, usage, pool_stats, footage_rows, rp, tts_info=None) -> dict:
    shots = [s for seg in plan["segments"] for s in seg["shots"]]
    r = ratios.measure(plan["segments"])
    f1 = ratios.check(r, cfg.footage_min, cfg.animation_max, cfg.text_max)
    caps = check_caps(shots, cfg.per_src_clips, cfg.per_src_secs, cfg.max_clip_s)
    bl = Blocklist()
    hits = [row for row in footage_rows if bl.check(row["channel"], row["channel_id"])]
    max_clip = max([s["dur"] for s in shots if s["template"] == "footage"] or [0])
    info = probe(video)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
    size_gb = video.stat().st_size / 1e9
    faces = [row["face_score"] for row in footage_rows if row.get("face_score") is not None]
    checks = {
        "f1_ratios": not f1, "f2_max_clip": max_clip <= min(cfg.max_clip_s, MAX_CLIP_SECONDS) + 1e-6,
        "f4_per_source": not caps, "f7_blocklist_hits_zero": not hits,
        "format_1080p30_h264": v.get("width") == 1920 and v.get("height") == 1080 and v.get("codec_name") == "h264"
                               and v.get("r_frame_rate") in ("30/1", "30000/1001"),
        "audio_aac_48k": a.get("codec_name") == "aac" and a.get("sample_rate") == "48000",
        "loudness_-14": abs(mix.get("lufs", 0) - (-14.0)) <= 1.5,
        "size_cap": size_gb <= cfg.get("max_output_gb", 1.0),
        "runtime_matches_plan": abs(duration(video) - plan["runtime"]) < 1.0,
    }
    q = {"runtime_s": round(duration(video), 2), "planned_runtime_s": plan["runtime"], "ratios": r, "f1_errors": f1,
         "max_clip_s": round(max_clip, 3), "per_source_errors": caps, "blocklist_hits": len(hits),
         "watermark_rejected": (pool_stats or {}).get("watermark_rejected", 0),
         "face_match": {"n": len(faces), "mean": round(sum(faces) / len(faces), 3) if faces else None,
                        "backend": (pool_stats or {}).get("face_backend")},
         "pool": {k: (pool_stats or {}).get(k) for k in ("pool_seconds", "pool_sources", "pool_ratio", "pool_ok")},
         "loudness_lufs": mix.get("lufs"), "true_peak": mix.get("true_peak"), "size_gb": round(size_gb, 4),
         "tts_chars": (tts_info or {}).get("chars_total"), "api_cost_usd": usage.totals()["usd"],
         "avg_shot_s": plan["avg_shot"], "checks": checks}
    q["overall"] = "OK" if all(checks.values()) else "CHECK"
    write_json(rp.o("qc.json"), q)
    return q
