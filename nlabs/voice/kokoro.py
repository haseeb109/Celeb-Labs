# voice/kokoro.py — Kokoro local TTS (free) fallback; used only if allow_voice_fallback.
# Install: pip install kokoro soundfile. Returns 24 kHz float audio; tts.py resamples.
# Voice "am_michael" approximates a warm authoritative narrator.
def synth(text: str, voice: str = "am_michael", speed: float = 1.0):
    from kokoro import KPipeline
    import numpy as np
    pipe = KPipeline(lang_code="a")
    chunks = [a for _, _, a in pipe(text, voice=voice, speed=speed)]
    return np.concatenate(chunks), 24000
