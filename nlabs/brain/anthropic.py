# brain/anthropic.py — Anthropic Messages API provider (optional).
# System messages are moved to the top-level "system" field as the API requires.
# Key lives in ~/.config/umf/anthropic.env.
import time
from .llm import Provider, Completion, BrainError


class Anthropic(Provider):
    name = "anthropic"

    def complete(self, messages, json_schema=None, max_tokens=4000, temperature=0.4, pass_name=""):
        if not self.key:
            raise BrainError("No API key for anthropic. Put it in ~/.config/umf/anthropic.env")
        import httpx
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        msgs = [m for m in messages if m["role"] != "system"]
        if json_schema is not None:
            system += "\n\nReply with ONE valid JSON object only."
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                "system": system, "messages": msgs}
        last = None
        for i in range(4):
            try:
                r = httpx.post("https://api.anthropic.com/v1/messages", json=body, timeout=180,
                               headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"})
                if r.status_code in (429, 500, 502, 503, 529):
                    raise BrainError(f"HTTP {r.status_code}")
                r.raise_for_status()
                d = r.json()
                text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
                u = d.get("usage", {})
                c = Completion(text=text, tokens_in=u.get("input_tokens", 0),
                               tokens_out=u.get("output_tokens", 0), model=self.model)
                self._record(pass_name, c)
                return c
            except Exception as e:
                last = e
                time.sleep(2 ** i)
        raise BrainError(f"anthropic failed: {last}")
