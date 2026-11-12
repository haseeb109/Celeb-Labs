# brain/llm.py — the provider interface for the LLM "brain".
# `get_brain(cfg)` returns a provider with `.complete(messages, json_schema, max_tokens,
# temperature)`. `run_pass()` adds JSON parsing, code validation and the repair loop.
from __future__ import annotations

from dataclasses import dataclass, field

from ..log import get_logger

log = get_logger()


@dataclass
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    raw: dict = field(default_factory=dict)


class BrainError(RuntimeError):
    pass


class NeedsManual(RuntimeError):
    """Manual brain: prompt written to disk, waiting for the owner to paste a reply."""


class NeedsReview(RuntimeError):
    """Brain failed validation after all repairs/attempts — stop gracefully."""


class Provider:
    name = "base"

    def __init__(self, model: str = "", key: str = "", usage=None, **kw):
        self.model = model
        self.key = key
        self.usage = usage
        self.opts = kw

    def complete(self, messages: list[dict], json_schema: dict | None = None,
                 max_tokens: int = 4000, temperature: float = 0.4, pass_name: str = "") -> Completion:
        raise NotImplementedError

    def _record(self, pass_name: str, c: Completion):
        if self.usage is not None:
            self.usage.brain(self.name, c.model or self.model, pass_name, c.tokens_in, c.tokens_out)


def get_brain(cfg, usage=None, name: str | None = None, run_paths=None) -> Provider:
    name = (name or cfg.get("brain_provider") or "deepseek").lower()
    model = cfg.get("brain_model") or ""
    keys = cfg.keys
    if name == "deepseek":
        from .deepseek import DeepSeek
        return DeepSeek(model=model or "deepseek-chat", key=keys.get("deepseek", ""), usage=usage)
    if name == "hive":
        from .hive import Hive
        return Hive(model=model or "deepseek-v3", key=keys.get("hive", ""), usage=usage)
    if name == "openai":
        from .openai import OpenAI
        m = model if model and not model.startswith("deepseek") else "gpt-4o-mini"
        return OpenAI(model=m, key=keys.get("openai", ""), usage=usage)
    if name == "anthropic":
        from .anthropic import Anthropic
        m = model if model.startswith("claude") else "claude-sonnet-5-5"
        return Anthropic(model=m, key=keys.get("anthropic", ""), usage=usage)
    if name == "manual":
        from .manual import Manual
        return Manual(folder=run_paths.manual_dir if run_paths else None, usage=usage)
    if name == "mock":
        from .mock import MockBrain
        return MockBrain(usage=usage)
    raise BrainError(f"unknown brain provider '{name}'")
