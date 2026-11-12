# package/cleanup.py — after a successful run: delete downloaded windows, frames and segment
# files (config cleanup_after_run). Keeps the TTS cache and all deliverables in output/.
import shutil


def run(rp, cfg):
    if not cfg.get("cleanup_after_run", True):
        return []
    removed = []
    for d in (rp.footage_dir, rp.stills_dir, rp.seg_dir):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            removed.append(str(d))
    for f in rp.work.glob("*.mp4"):
        f.unlink()
    return removed
