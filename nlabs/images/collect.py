# images/collect.py — Station 5 runner: licensed photos + stills from the footage pool.
# Stills = sharpest frames where the subject's face matched (F8). Generic photos only for
# B-roll keywords. Writes images.json + image_credits.txt. Network failures fall through.
from __future__ import annotations

from ..log import get_logger
from ..util import write_json, read_json, sha1
from ..paths import cache_dir
from . import wikimedia, pexels, pixabay, flickr, official_photos, credits

log = get_logger()


def _download(url, referer=None):
    p = cache_dir("images") / (sha1(url) + ".jpg")
    if p.exists():
        return p
    from ..util import http_client
    with http_client() as c:
        r = c.get(url, headers={"Referer": referer} if referer else {})
        r.raise_for_status()
        p.write_bytes(r.content)
    return p


def extract_stills(pool: dict, rp, n: int = 12) -> list[dict]:
    import cv2
    out = []
    clips = sorted([c for c in pool.get("clips", []) if c.get("subject_present")] or pool.get("clips", []),
                   key=lambda c: (c.get("face_score", 0), c.get("sharpness", 0)), reverse=True)
    for c in clips[:n]:
        cap = cv2.VideoCapture(c["path"])
        t = (c["in"] + c["out"]) / 2
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, f = cap.read()
        cap.release()
        if not ok:
            continue
        if c.get("crop"):
            h, w = f.shape[:2]
            x0, y0, x1, y1 = c["crop"]
            f = f[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        p = rp.stills_dir / f"still_{c['clip_id']}.jpg"
        cv2.imwrite(str(p), f, [cv2.IMWRITE_JPEG_QUALITY, 92])
        out.append({"source": "still", "path": str(p), "clip_id": c["clip_id"], "subject": c.get("subject_present"),
                    "face_score": c.get("face_score", 0), "face_box": c.get("face_box"), "channel": c["channel"],
                    "url": c["url"], "t": c["src_in"] + t - c["in"], "tier": c["tier"], "video_id": c["video_id"]})
    return out


def run_images(subject: str, keywords: list[str], pool: dict, cfg, rp) -> list[dict]:
    if rp.is_done("images"):
        return read_json(rp.w("images.json"), [])
    images = extract_stills(pool, rp)
    found = official_photos.load()
    try:
        found += [x | {"subject": True} for x in wikimedia.search(subject, 8)]
    except Exception as e:
        log.info(f"wikimedia unavailable: {type(e).__name__}")
    if cfg.keys.get("flickr"):
        try:
            found += flickr.search(subject, cfg.keys["flickr"], 8)
        except Exception as e:
            log.info(f"flickr unavailable: {type(e).__name__}")
    for kw in keywords[:6]:
        for prov, key in ((pexels, "pexels"), (pixabay, "pixabay")):
            if cfg.keys.get(key):
                try:
                    found += [x | {"keyword": kw} for x in prov.search(kw, cfg.keys[key], 3)]
                    break   # rate limit / error → next provider in chain
                except Exception:
                    continue
    for im in found:
        try:
            im["path"] = str(_download(im["url"], im.get("referer")))
            if im.get("generic") and cfg.get("stylize_generic_photos"):
                import cv2
                from .stylize import stylize
                cv2.imwrite(im["path"], stylize(cv2.imread(im["path"])))
                im["modified"] = True
            images.append(im)
        except Exception as e:
            log.info(f"image download failed {im.get('url', '')[:60]}: {type(e).__name__}")
    write_json(rp.w("images.json"), images)
    credits.write(images, rp.o("image_credits.txt"))
    rp.mark_done("images")
    return images
