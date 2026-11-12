# voice/whisper_timing.py — word timings when the TTS transcript is missing/failed.
# faster-whisper (Windows/CUDA/CPU) → mlx-whisper (Mac) → even spread estimate.
# Output: [{"w", "start", "end"}] relative to the audio file.
from __future__ import annotations


def words_from_audio(path: str, text: str = "", dur: float = 0.0) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel("base.en", device="auto", compute_type="int8")
        segs, _ = m.transcribe(path, word_timestamps=True, language="en")
        out = [{"w": w.word.strip(), "start": w.start, "end": w.end} for s in segs for w in (s.words or [])]
        if out:
            return out
    except Exception:
        pass
    try:
        import mlx_whisper
        r = mlx_whisper.transcribe(path, word_timestamps=True)
        out = [{"w": w["word"].strip(), "start": w["start"], "end": w["end"]}
               for s in r.get("segments", []) for w in s.get("words", [])]
        if out:
            return out
    except Exception:
        pass
    return estimate(text, dur)


def estimate(text: str, dur: float, lead: float = 0.0) -> list[dict]:
    """Spread words over the duration weighted by length (used by dummy TTS too)."""
    ws = text.split()
    if not ws or dur <= 0:
        return []
    weights = [len(w) + 2 for w in ws]
    tot = sum(weights)
    t, out = lead, []
    for w, k in zip(ws, weights):
        d = (dur - lead) * k / tot
        out.append({"w": w, "start": round(t, 3), "end": round(t + d * 0.92, 3)})
        t += d
    return out
