# voice/ai33.py — ai33.pro TTS client: POST /v3/text-to-speech → poll /v1/task/{id} every 4 s
# → download audio_url (mp3) + json_url (word timings). transcript_status=="failed" counts
# as done (whisper computes timings). Downloads retried 6x with back-off.
from __future__ import annotations

import time

BASE = "https://api.ai33.pro"


class Ai33Error(RuntimeError):
    pass


def synth(text: str, voice_id: str, speed: float, key: str, client=None, poll_s: float = 4.0,
          timeout_s: float = 300) -> tuple[bytes, dict | None]:
    import httpx
    c = client or httpx.Client(timeout=60)
    r = c.post(f"{BASE}/v3/text-to-speech", headers={"xi-api-key": key},
               data={"text": text, "voice_id": voice_id, "speed": str(speed), "with_transcript": "true"})
    if r.status_code >= 400:
        raise Ai33Error(f"ai33 HTTP {r.status_code}: {r.text[:200]}")
    task_id = r.json().get("task_id")
    if not task_id:
        raise Ai33Error(f"ai33: no task_id in {r.text[:200]}")
    t0 = time.time()
    while True:
        if time.time() - t0 > timeout_s:
            raise Ai33Error(f"ai33 task {task_id} stuck > {timeout_s:.0f}s")
        time.sleep(poll_s)
        s = c.get(f"{BASE}/v1/task/{task_id}", headers={"xi-api-key": key}).json()
        if s.get("status") == "failed":
            raise Ai33Error(f"ai33 task failed: {str(s)[:200]}")
        if s.get("status") == "done":
            md = s.get("metadata", {})
            audio = _get(c, md["audio_url"])
            timings = None
            if md.get("json_url") and md.get("transcript_status") != "failed":
                try:
                    timings = __import__("json").loads(_get(c, md["json_url"]))
                except Exception:
                    timings = None
            return audio, timings


def _get(c, url):
    last = None
    for i in range(6):
        try:
            r = c.get(url, timeout=60)
            r.raise_for_status()
            return r.content
        except Exception as e:
            last = e
            time.sleep(1.5 * 2 ** i)
    raise Ai33Error(f"download failed: {last}")


def parse_timings(d) -> list[dict] | None:
    """Accept word lists or ElevenLabs-style character alignment."""
    if not d:
        return None
    if isinstance(d, dict):
        for k in ("words", "word_timestamps", "transcript"):
            if isinstance(d.get(k), list):
                d = d[k]; break
        else:
            al = d.get("alignment") or d.get("normalized_alignment") or d
            ch = al.get("characters")
            if ch:
                st, en = al["character_start_times_seconds"], al["character_end_times_seconds"]
                words, cur, ws = [], "", None
                for c_, a, b in zip(ch, st, en):
                    if c_.isspace():
                        if cur:
                            words.append({"w": cur, "start": ws, "end": prev}); cur = ""
                    else:
                        if not cur:
                            ws = a
                        cur += c_; prev = b
                if cur:
                    words.append({"w": cur, "start": ws, "end": prev})
                return words
            return None
    out = []
    for w in d:
        t = w.get("word") or w.get("text") or w.get("w")
        s = w.get("start") if w.get("start") is not None else w.get("start_time")
        e = w.get("end") if w.get("end") is not None else w.get("end_time")
        if t is not None and s is not None:
            out.append({"w": t.strip(), "start": float(s), "end": float(e if e is not None else s)})
    return out or None
