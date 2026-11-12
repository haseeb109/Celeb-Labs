# vision/check.py — asks a vision model: "Does every labeled subject shot show <subject>?
# Any visible logos/watermarks/chyrons?" → flags. Default provider "human" = the owner
# reviews contact_sheet_plan.jpg at the plan gate. Flags never loosen code rules.
from __future__ import annotations

import base64
import json


QUESTION = ("This is a contact sheet of video shots. Labels show shot ids. Does every shot labeled as the subject show "
            "{subject}? Are there any visible TV-channel logos, watermarks, chyrons, tickers or burned-in captions? "
            'Reply JSON: {{"flags":[{{"shot_id":"sh0001","problem":"..."}}]}}')


def check(sheet_path, subject, cfg) -> dict:
    prov = (cfg.get("vision_provider") or "human").lower()
    if prov == "human":
        return {"provider": "human", "flags": [], "note": f"Review {sheet_path} at the plan gate"}
    img = base64.b64encode(open(sheet_path, "rb").read()).decode()
    q = QUESTION.format(subject=subject)
    import httpx
    try:
        if prov == "gemini":
            r = httpx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                           params={"key": cfg.keys.get("gemini", "")}, timeout=90,
                           json={"contents": [{"parts": [{"text": q}, {"inline_data": {"mime_type": "image/jpeg", "data": img}}]}]})
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        elif prov == "anthropic":
            r = httpx.post("https://api.anthropic.com/v1/messages", timeout=90,
                           headers={"x-api-key": cfg.keys.get("anthropic", ""), "anthropic-version": "2023-06-01"},
                           json={"model": "claude-sonnet-5-5", "max_tokens": 1000, "messages": [{"role": "user", "content": [
                               {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img}},
                               {"type": "text", "text": q}]}]})
            text = r.json()["content"][0]["text"]
        elif prov == "ollama":
            r = httpx.post("http://localhost:11434/api/generate", timeout=300,
                           json={"model": "qwen2.5vl", "prompt": q, "images": [img], "stream": False})
            text = r.json()["response"]
        else:
            return {"provider": prov, "flags": [], "note": "unknown provider"}
        from ..brain.repair import extract_json
        return {"provider": prov} | extract_json(text)
    except Exception as e:
        return {"provider": prov, "flags": [], "error": str(e)[:200]}
