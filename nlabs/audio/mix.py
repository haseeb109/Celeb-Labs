# audio/mix.py — builds the full soundtrack from the edit plan: VO at segment start + lead,
# soundbites from the source clip (50 ms fades, RMS-matched to VO), synthesized SFX on cards
# and stamps, music ducked to −20 dB under speech / −12 dB on cards (400 ms smoothing), loudnorm.
from __future__ import annotations

import functools
import wave

import numpy as np

from ..constants import AUDIO_RATE as SR
from ..util import ffmpeg
from . import sfx, music, loudness


def read_wav(path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n, ch = w.getnframes(), w.getnchannels()
        a = np.frombuffer(w.readframes(n), "<i2").astype(np.float32) / 32768
    a = a.reshape(-1, ch)
    return a if ch == 2 else np.repeat(a, 2, axis=1)


def write_wav(path, a: np.ndarray):
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def clip_audio(path, t_in, dur, work_dir) -> np.ndarray:
    out = work_dir / f"sb_{abs(hash((path, t_in, dur))) % 10**8}.wav"
    try:
        ffmpeg(["-ss", f"{t_in:.3f}", "-i", str(path), "-t", f"{dur:.3f}", "-vn", "-ar", str(SR), "-ac", "2",
                "-c:a", "pcm_s16le", str(out)])
        return read_wav(out)
    except Exception:
        return np.zeros((int(dur * SR), 2), np.float32)


def rms(a):
    return float(np.sqrt(np.mean(a ** 2)) + 1e-9) if len(a) else 1e-9


def fade(a, ms=50):
    n = min(int(ms / 1000 * SR), len(a) // 2)
    if n > 0:
        r = np.linspace(0, 1, n, dtype=np.float32)[:, None]
        a[:n] *= r
        a[-n:] *= r[::-1]
    return a


def add(buf, a, at_s, gain=1.0):
    i = int(at_s * SR)
    if i >= len(buf) or len(a) == 0:
        return
    j = min(len(buf), i + len(a))
    buf[i:j] += a[: j - i] * gain


def db(x):
    return 10 ** (x / 20)


@functools.lru_cache(maxsize=1)
def _sfx():
    return {"whoosh": sfx.whoosh(), "boom": sfx.boom(), "type": sfx.typewriter(2.5), "tick": sfx.clock(2.0)}


def build_mix(plan: dict, rp, cfg) -> dict:
    total = plan["runtime"]
    n = int(total * SR) + SR
    voice = np.zeros((n, 2), np.float32)
    fx = np.zeros((n, 2), np.float32)
    speech = np.zeros(n, np.float32)
    card = np.zeros(n, np.float32)
    S = _sfx()
    vo_rms = []
    for seg in plan["segments"]:
        a = seg["audio"]
        if a.get("vo"):
            v = read_wav(a["vo"])
            add(voice, v, seg["start"] + a.get("lead", 0.1))
            i = int((seg["start"] + a.get("lead", 0.1)) * SR)
            speech[i:i + len(v)] = 1
            vo_rms.append(rms(v))
    ref = float(np.median(vo_rms)) if vo_rms else 0.1
    for seg in plan["segments"]:
        t = seg["start"]
        for sh in seg["shots"]:
            if sh.get("audio_from_source"):
                sb = fade(clip_audio(sh["path"], sh["in"], sh["dur"], rp.audio_dir), 50)
                add(voice, sb, t, gain=ref / rms(sb))
                i = int(t * SR)
                speech[i:i + len(sb)] = 1
            if sh["template"] in ("chapter", "title"):
                add(fx, S["whoosh"], t, 0.5)
            if sh["template"] in ("quote_card", "statement_card", "post_card"):
                add(fx, S["type"][: int(min(sh["dur"], 2.5) * SR)], t, 0.18)
            if sh.get("overlay", {}).get("stamp") or sh["template"] == "stamp":
                add(fx, S["boom"], t, 0.45)
            if sh["template"] in ("counter", "calendar"):
                add(fx, S["tick"], t, 0.2)
            if sh["category"] != "footage" or sh["template"] in ("title", "chapter", "endscreen"):
                card[int(t * SR):int((t + sh["dur"]) * SR)] = 1
            t += sh["dur"]
    bed, credits = music.bed(total + 1, rp.audio_dir, cfg.style_get("music", "mood", default=""))
    bed = bed[:n] if len(bed) >= n else np.pad(bed, ((0, n - len(bed)), (0, 0)))
    duck_db = cfg.style_get("music", "duck_db", default=-20)
    target = np.where(speech > 0, db(duck_db), np.where(card > 0, db(-12), db(-14))).astype(np.float32)
    k = int(0.4 * SR)
    kern = np.ones(k, np.float32) / k
    env = np.convolve(target, kern, mode="same")[:n]
    bed *= (env / max(np.abs(bed).max(), 1e-6) * 0.9)[:, None] if np.abs(bed).max() > 0 else 0
    mixed = voice + fx + bed
    raw = rp.w("mix_raw.wav")
    write_wav(raw, mixed[: int(total * SR)])
    norm = rp.w("mix.wav")
    meas = loudness.normalize(raw, norm, -14.0)
    return {"path": str(norm), "lufs": float(meas.get("input_i", 0) or 0), "true_peak": float(meas.get("input_tp", 0) or 0),
            "music_credits": credits}
