# usage.py — the API cost ledger (tokens, characters, credits, $ estimates).
# Every paid call records itself here; the ledger is printed as BRAIN USAGE at
# the end of a run and saved to usage.json. Prices come from config.json "prices".
from __future__ import annotations

import json
import threading
from pathlib import Path


class Usage:
    def __init__(self, prices: dict | None = None):
        self.prices = prices or {}
        self.rows: list[dict] = []
        self._lock = threading.Lock()

    def brain(self, provider: str, model: str, pass_name: str, tok_in: int, tok_out: int):
        p = self.prices.get(model, {})
        usd = tok_in / 1e6 * p.get("in_per_mtok", 0) + tok_out / 1e6 * p.get("out_per_mtok", 0)
        self._add(kind="brain", provider=provider, model=model, pass_name=pass_name,
                  tokens_in=tok_in, tokens_out=tok_out, usd=round(usd, 5))

    def tts(self, provider: str, chars: int, cached: bool):
        usd = 0.0 if cached else chars / 1000 * self.prices.get("ai33_tts_per_1k_chars", 0)
        self._add(kind="tts", provider=provider, chars=chars, cached=cached, usd=round(usd, 5))

    def search(self, provider: str, n: int = 1):
        usd = n * self.prices.get(f"{provider}_per_query", 0)
        self._add(kind="search", provider=provider, queries=n, usd=round(usd, 5))

    def _add(self, **row):
        with self._lock:
            self.rows.append(row)

    def totals(self) -> dict:
        t = {"usd": 0.0, "tokens_in": 0, "tokens_out": 0, "tts_chars": 0, "tts_chars_paid": 0, "searches": 0}
        for r in self.rows:
            t["usd"] += r.get("usd", 0)
            t["tokens_in"] += r.get("tokens_in", 0)
            t["tokens_out"] += r.get("tokens_out", 0)
            if r["kind"] == "tts":
                t["tts_chars"] += r["chars"]
                if not r["cached"]:
                    t["tts_chars_paid"] += r["chars"]
            if r["kind"] == "search":
                t["searches"] += r["queries"]
        t["usd"] = round(t["usd"], 4)
        return t

    def report(self) -> str:
        t = self.totals()
        lines = ["BRAIN USAGE"]
        by_pass: dict[str, list[int]] = {}
        for r in self.rows:
            if r["kind"] == "brain":
                v = by_pass.setdefault(r["pass_name"], [0, 0])
                v[0] += r["tokens_in"]; v[1] += r["tokens_out"]
        for k, (a, b) in by_pass.items():
            lines.append(f"  {k:<22} in {a:>8}  out {b:>7}")
        lines.append(f"  TTS chars {t['tts_chars']} (paid {t['tts_chars_paid']}) · searches {t['searches']}")
        lines.append(f"  Estimated cost: ${t['usd']:.4f}")
        return "\n".join(lines)

    def save(self, path: Path, merge: bool = True):
        rows = self.rows
        if merge and path.exists():
            try:
                old = json.loads(path.read_text())
                rows = old.get("rows", []) + [r for r in self.rows if r not in old.get("rows", [])]
            except Exception:
                pass
        self.rows = rows
        path.write_text(json.dumps({"totals": self.totals(), "rows": rows}, indent=2))
