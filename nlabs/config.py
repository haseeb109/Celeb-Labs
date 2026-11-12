# config.py — loads config.json, the chosen style pack, and API keys.
# Keys come ONLY from ~/.config/umf/*.env (never the project folder). Locked
# values are passed through constants.tighten() so config can only make them stricter.
from __future__ import annotations

import json
import os
import stat
import copy
from pathlib import Path

from . import constants as C
from .paths import ROOT, STYLES, KEY_DIR

KEY_FILES = ["deepseek", "ai33", "brave", "tavily", "pexels", "pixabay", "gemini",
             "anthropic", "openai", "hive", "flickr"]


def _read_env(path: Path) -> dict[str, str]:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_keys(key_dir: Path | None = None) -> dict[str, str]:
    """Return {provider: key}. Env var <PROVIDER>_API_KEY overrides the file."""
    key_dir = key_dir or KEY_DIR
    keys = {}
    for name in KEY_FILES:
        env = _read_env(key_dir / f"{name}.env")
        val = os.environ.get(f"{name.upper()}_API_KEY") or env.get(f"{name.upper()}_API_KEY") \
            or next(iter(env.values()), "")
        if val:
            keys[name] = val
    return keys


def ensure_key_templates(key_dir: Path | None = None):
    """Create empty key files with user-only permissions (setup step)."""
    key_dir = key_dir or KEY_DIR
    key_dir.mkdir(parents=True, exist_ok=True)
    for name in KEY_FILES:
        p = key_dir / f"{name}.env"
        if not p.exists():
            p.write_text(f"# Paste your key after the = sign\n{name.upper()}_API_KEY=\n", encoding="utf-8")
        try:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # Windows: Setup.bat applies an icacls user-only ACL


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def list_styles() -> list[str]:
    return sorted(p.name for p in STYLES.iterdir() if (p / "style.json").exists())


class Config:
    """Merged view of config.json + style.json + CLI overrides + locked rules."""

    def __init__(self, style: str = "news_explainer", overrides: dict | None = None,
                 config_path: Path | None = None):
        self.raw = json.loads((config_path or ROOT / "config.json").read_text(encoding="utf-8"))
        self.raw = deep_merge(self.raw, overrides or {})
        self.style_name = style
        self.style_dir = STYLES / style
        if not (self.style_dir / "style.json").exists():
            raise FileNotFoundError(f"Style '{style}' not found. Available: {list_styles()}")
        self.style = json.loads((self.style_dir / "style.json").read_text(encoding="utf-8"))
        self.keys = load_keys()
        self._apply_locks()

    def _apply_locks(self):
        r, s = self.raw, self.style
        self.max_clip_s = C.tighten("clip", r.get("max_clip_seconds"), C.MAX_CLIP_SECONDS, "lower")
        ratios = s.get("ratios", {})
        self.footage_min = C.tighten("fmin", ratios.get("footage_min"), C.FOOTAGE_MIN_RATIO, "higher")
        self.animation_max = C.tighten("amax", ratios.get("animation_max"), C.ANIMATION_MAX_RATIO, "lower")
        self.text_max = C.tighten("tmax", ratios.get("text_cards_max"), C.TEXT_CARDS_MAX_RATIO, "lower")
        self.pool_mult = C.tighten("pool", r.get("footage_pool_multiplier"), C.POOL_MULTIPLIER_MIN, "higher")
        self.min_sources = C.tighten("srcs", r.get("min_source_videos"), C.MIN_SOURCE_VIDEOS, "higher")
        self.per_src_clips = C.tighten("pc", r.get("per_source_max_clips"), C.PER_SOURCE_MAX_CLIPS, "lower")
        self.per_src_secs = C.tighten("ps", r.get("per_source_max_seconds"), C.PER_SOURCE_MAX_SECONDS, "lower")
        self.crop_min_area = C.tighten("crop", r.get("watermark_crop_min_area"), C.WATERMARK_CROP_MIN_AREA, "higher")
        self.face_threshold = C.tighten("face", r.get("face_threshold"), C.FACE_THRESHOLD_COSINE, "higher")
        self.tts_confirm_chars = C.tighten("tts", r.get("tts_confirm_chars"), C.TTS_CONFIRM_CHARS, "lower")

    def get(self, key, default=None):
        return self.raw.get(key, default)

    def style_get(self, *path, default=None):
        node = self.style
        for p in path:
            if not isinstance(node, dict) or p not in node:
                return default
            node = node[p]
        return node

    def color(self, name: str) -> tuple[int, int, int]:
        pal = self.style.get("palette", {})
        hexv = pal.get(name, name if str(name).startswith("#") else "#FFFFFF")
        hexv = hexv.lstrip("#")
        return tuple(int(hexv[i:i + 2], 16) for i in (0, 2, 4))

    def prompt_path(self, name: str) -> Path:
        return self.style_dir / "prompts" / name

    @property
    def workers(self) -> int:
        n = int(self.raw.get("parallel_workers") or 0)
        if n <= 0:
            n = min(max((os.cpu_count() or 4) - 2, 1), 8)
        return min(n, 8)
