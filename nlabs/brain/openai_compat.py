# brain/openai_compat.py — shared code for OpenAI-style chat-completion APIs.
# DeepSeek, Hive and OpenAI all speak this format; each subclass only sets the
# base URL. Uses JSON mode when a schema is requested; the code still validates.
from __future__ import annotations

import time

from .llm import Provider, Completion, BrainError


class OpenAICompat(Provider):
    name = "openai_compat"
    base_url = ""

    def complete(self, messages, json_schema=None, max_tokens=4000, temperature=0.4, pass_name=""):
        if not self.key:
            raise BrainError(f"No API key for {self.name}. Put it in ~/.config/umf/{self.name}.env")
        import httpx
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                "temperature": temperature}
        if json_schema is not None:
            body["response_format"] = {"type": "json_object"}
        last = None
        for i in range(4):
            try:
                r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=180,
                               headers={"Authorization": f"Bearer {self.key}"})
                if r.status_code in (429, 500, 502, 503, 504):
                    raise BrainError(f"HTTP {r.status_code}")
                r.raise_for_status()
                d = r.json()
                u = d.get("usage", {})
                c = Completion(text=d["choices"][0]["message"]["content"] or "",
                               tokens_in=u.get("prompt_tokens", 0), tokens_out=u.get("completion_tokens", 0),
                               model=d.get("model", self.model), raw={})
                self._record(pass_name, c)
                return c
            except Exception as e:  # network or 5xx -> back-off
                last = e
                time.sleep(2 ** i)
        raise BrainError(f"{self.name} failed: {last}")
