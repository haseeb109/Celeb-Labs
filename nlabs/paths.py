# paths.py — where everything lives: project root, caches, run folders, key folder.
# One place to change folder layout. Run folders are work/<run_id>/ (scratch)
# and output/<YYYY-MM-DD>_<slug>/ (deliverables).
from __future__ import annotations

import os
import re
import datetime as _dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
WORK = ROOT / "work"
OUTPUT = ROOT / "output"
STYLES = ROOT / "styles"
ASSETS = ROOT / "assets"
BIN = ROOT / "bin"
TESTS = ROOT / "tests"
KEY_DIR = Path(os.environ.get("UMF_KEY_DIR", Path.home() / ".config" / "umf"))


def slugify(text: str, max_len: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (s[:max_len].rstrip("-")) or "untitled"


def new_run_id(topic: str) -> str:
    return f"{_dt.date.today().isoformat()}_{slugify(topic, 48)}"


class RunPaths:
    """All folders for one run. Creating it is idempotent (resume-friendly)."""

    def __init__(self, run_id: str, base_work: Path | None = None, base_out: Path | None = None):
        self.run_id = run_id
        self.work = (base_work or WORK) / run_id
        self.out = (base_out or OUTPUT) / run_id
        for p in (self.work, self.out, self.seg_dir, self.audio_dir, self.footage_dir,
                  self.stills_dir, self.manual_dir, self.markers):
            p.mkdir(parents=True, exist_ok=True)

    @property
    def seg_dir(self): return self.work / "seg"
    @property
    def audio_dir(self): return self.work / "audio"
    @property
    def footage_dir(self): return self.work / "footage"
    @property
    def stills_dir(self): return self.work / "stills"
    @property
    def manual_dir(self): return self.work / "manual"
    @property
    def markers(self): return self.work / "done"

    def w(self, name: str) -> Path: return self.work / name
    def o(self, name: str) -> Path: return self.out / name

    # P1 resume markers
    def is_done(self, station: str) -> bool: return (self.markers / station).exists()
    def mark_done(self, station: str): (self.markers / station).write_text(_dt.datetime.now().isoformat())
    def clear_done(self, station: str):
        m = self.markers / station
        if m.exists():
            m.unlink()


def cache_dir(name: str) -> Path:
    p = CACHE / name
    p.mkdir(parents=True, exist_ok=True)
    return p
