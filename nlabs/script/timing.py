# script/timing.py — characters-per-second calibration for length targeting.
# Default 15 chars/s; after the first TTS batch the measured rate per voice is stored
# in cache/tts/calibration.json and used for later runs.
from ..paths import cache_dir
from ..util import read_json, write_json

DEFAULT_CPS = 15.0


def chars_per_sec(voice_id: str, speed: float = 1.0) -> float:
    d = read_json(cache_dir("tts") / "calibration.json", {}) or {}
    return float(d.get(f"{voice_id}@{speed}", DEFAULT_CPS))


def calibrate(voice_id: str, speed: float, chars: int, seconds: float):
    if seconds <= 1 or chars < 200:
        return
    p = cache_dir("tts") / "calibration.json"
    d = read_json(p, {}) or {}
    d[f"{voice_id}@{speed}"] = round(chars / seconds, 2)
    write_json(p, d)
