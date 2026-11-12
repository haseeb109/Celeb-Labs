# package/footage_log.py — Rule P3: footage_log.csv with every clip used: source URL, channel,
# channel ID, tier, license, in/out, on-screen seconds, treatment, watermark scan, face score.
# Background clips behind cards and split-screen second clips are logged too.
import csv


FIELDS = ["shot_id", "segment", "timeline_start", "on_screen_s", "url", "channel", "channel_id", "tier", "license",
          "src_in", "src_out", "treatment", "watermark_scan", "crop", "face_score", "role"]


def rows(plan):
    out = []
    for seg in plan["segments"]:
        t = seg["start"]
        for sh in seg["shots"]:
            items = []
            if sh["template"] == "footage":
                items.append((sh, "main"))
                if sh.get("second"):
                    items.append((sh["second"], "split-second"))
            if (sh.get("bg") or {}).get("kind") == "clip":
                items.append((sh["bg"], "card-background"))
            for src, role in items:
                out.append({"shot_id": sh["shot_id"], "segment": seg["seg_id"], "timeline_start": round(t, 2),
                            "on_screen_s": round(sh["dur"], 2), "url": src.get("url", ""), "channel": src.get("channel", ""),
                            "channel_id": src.get("channel_id", sh.get("channel_id", "")), "tier": src.get("tier", ""),
                            "license": src.get("license", ""), "src_in": round(src.get("src_in", 0), 2),
                            "src_out": round(src.get("src_in", 0) + sh["dur"], 2), "treatment": sh.get("treatment", role),
                            "watermark_scan": src.get("watermark", ""), "crop": src.get("crop"),
                            "face_score": src.get("face_score"), "role": role})
            t += sh["dur"]
    return out


def write(plan, path):
    r = rows(plan)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(r)
    return r
