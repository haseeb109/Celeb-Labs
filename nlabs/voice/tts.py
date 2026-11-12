# voice/tts.py — Station 6 runner. Rule V1: count characters FIRST and stop before any
# TTS call if > 5,000 without confirmation. Rule V2: cache by sha1(voice+speed+text).
# Every segment → 48 kHz stereo WAV + word timings (voice.json). Concurrency 3.
from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..constants import AUDIO_RATE, LockedRuleError
from ..log import get_logger
from ..paths import cache_dir
from ..util import sha1, ffmpeg, duration, write_json, read_json
from . import ai33, whisper_timing
from ..script.timing import calibrate

log = get_logger()
SPOKEN = ("vo", "post", "statement")


class TTSBudgetStop(LockedRuleError):
    """V1: run stopped before any TTS call."""


def spoken_segments(script):
    return [s for s in script["segments"] if s["kind"] in SPOKEN and s.get("text")]


def tts_chars(script) -> int:
    return sum(len(s["text"]) for s in spoken_segments(script))


def cache_key(voice_id, speed, text):
    return sha1(voice_id, speed, text)


def budget_gate(script, cfg, confirm: bool, voice_id: str, speed: float, ask=None) -> dict:
    """V1 gate. Characters already in the TTS cache are free and not counted."""
    segs = spoken_segments(script)
    total = sum(len(s["text"]) for s in segs)
    new = sum(len(s["text"]) for s in segs
              if not (cache_dir("tts") / f"{cache_key(voice_id, speed, s['text'])}.wav").exists())
    price = cfg.get("prices", {}).get("ai33_tts_per_1k_chars", 0)
    info = {"chars_total": total, "chars_new": new, "est_usd": round(new / 1000 * price, 3),
            "limit": cfg.tts_confirm_chars}
    if new > cfg.tts_confirm_chars and not confirm:
        if ask is not None:
            ok = ask(f"TTS needs {new:,} new characters (≈${info['est_usd']}). Over the {cfg.tts_confirm_chars:,} "
                     f"limit. Continue? [y/N] ")
            if ok:
                info["confirmed"] = "prompt"
                return info
        raise TTSBudgetStop(f"V1: {new:,} TTS characters > {cfg.tts_confirm_chars:,}. Re-run with --confirm-tts "
                            f"(≈${info['est_usd']} estimated). No TTS call was made.")
    return info


def _to_wav(src, dst, pad_s=0.0):
    ffmpeg(["-i", str(src), "-ar", str(AUDIO_RATE), "-ac", "2", "-c:a", "pcm_s16le", str(dst)])


def dummy_wav(text: str, path, cps: float = 15.0):
    """Silent-ish test voice (very low noise so loudness tools behave)."""
    dur = max(1.0, len(text) / cps)
    n = int(dur * AUDIO_RATE)
    rng = np.random.default_rng(len(text))
    t = np.arange(n) / AUDIO_RATE
    # gentle syllable-like envelope so ducking/loudness are exercised
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 3.2 * t) ** 2
    sig = (rng.standard_normal(n) * 0.02 + 0.05 * np.sin(2 * np.pi * 140 * t)) * env
    pcm = (np.clip(np.stack([sig, sig], 1), -1, 1) * 32767).astype("<i2")
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(AUDIO_RATE); w.writeframes(pcm.tobytes())
    return dur


def synth_one(seg, provider, voice_id, speed, cfg, usage):
    text = seg["text"]
    key = cache_key(voice_id if provider != "dummy" else "dummy", speed, text)
    wav = cache_dir("tts") / f"{key}.wav"
    tjs = cache_dir("tts") / f"{key}.json"
    if wav.exists() and tjs.exists():
        if usage:
            usage.tts(provider, len(text), cached=True)
        return wav, read_json(tjs)
    words = None
    if provider == "dummy":
        d = dummy_wav(text, wav)
        words = whisper_timing.estimate(text, d)
    elif provider == "ai33":
        try:
            audio, timings = _ai33_with_retry(text, voice_id, speed, cfg)
        except Exception as e:
            if not cfg.get("allow_voice_fallback"):
                raise RuntimeError(f"ai33 failed for {seg['id']} ({e}); set allow_voice_fallback to use Kokoro") from e
            log.warning(f"ai33 failed for {seg['id']}; Kokoro fallback for this segment only")
            return synth_one(seg, "kokoro", voice_id, speed, cfg, usage)
        mp3 = wav.with_suffix(".mp3")
        mp3.write_bytes(audio)
        _to_wav(mp3, wav)
        words = ai33.parse_timings(timings)
        if usage:
            usage.tts("ai33", len(text), cached=False)
    elif provider == "kokoro":
        from . import kokoro
        a, sr = kokoro.synth(text)
        import soundfile as sf
        tmp = wav.with_suffix(".k.wav")
        sf.write(str(tmp), a, sr)
        _to_wav(tmp, wav)
        tmp.unlink()
    elif provider == "os":
        from .os_voice import synth_to_file
        tmp = str(wav.with_suffix(".os.wav"))
        if not synth_to_file(text, tmp):
            raise RuntimeError("OS voice unavailable")
        _to_wav(tmp if shutil.os.path.exists(tmp) else tmp.replace(".wav", ".aiff"), wav)
    d = duration(wav)
    if not words:
        words = whisper_timing.words_from_audio(str(wav), text, d) if provider != "dummy" else \
            whisper_timing.estimate(text, d)
    write_json(tjs, words)
    return wav, words


def _ai33_with_retry(text, voice_id, speed, cfg):
    key = cfg.keys.get("ai33")
    if not key:
        raise RuntimeError("No ai33 key in ~/.config/umf/ai33.env")
    try:
        return ai33.synth(text, voice_id, speed, key)
    except ai33.Ai33Error:
        return ai33.synth(text, voice_id, speed, key)   # retry once (stuck/failed)


def run_tts(script, cfg, rp, usage, confirm=False, provider=None, ask=None) -> dict:
    if rp.is_done("voice"):
        return read_json(rp.w("voice.json"))
    v = cfg.style.get("voice", {})
    provider = provider or cfg.get("tts_provider") or v.get("provider", "ai33")
    voice_id, speed = v.get("voice_id", ""), float(v.get("speed", 1.0))
    gate = budget_gate(script, cfg, confirm, voice_id if provider != "dummy" else "dummy", speed, ask)
    log.info(f"TTS: {gate['chars_total']:,} chars ({gate['chars_new']:,} new) via {provider}")
    segs = spoken_segments(script)
    out = {"provider": provider, "gate": gate, "segments": {}}

    def job(seg):
        wav, words = synth_one(seg, provider, voice_id, speed, cfg, usage)
        dst = rp.audio_dir / f"{seg['id']}.wav"
        shutil.copyfile(wav, dst)
        return seg["id"], {"wav": str(dst), "duration": round(duration(dst), 3), "words": words}

    with ThreadPoolExecutor(max_workers=int(cfg.get("tts_concurrency", 3))) as ex:
        for sid, res in ex.map(job, segs):
            out["segments"][sid] = res
    chars = sum(len(s["text"]) for s in segs)
    secs = sum(r["duration"] for r in out["segments"].values())
    if provider != "dummy":
        calibrate(voice_id, speed, chars, secs)
    write_json(rp.w("voice.json"), out)
    rp.mark_done("voice")
    return out
