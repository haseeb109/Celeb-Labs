# brain/repair.py — JSON extraction + the validate→repair→retry loop.
# Exact validator errors are sent back (max N repair rounds, reply capped at 1.3x the
# previous size to stop loops); after that a fresh attempt; after all attempts → NeedsReview.
from __future__ import annotations

import json
import re
from typing import Callable

from .llm import Provider, NeedsReview, NeedsManual, BrainError
from ..log import get_logger

log = get_logger()


def extract_json(text: str):
    """Pull the first JSON object/array out of a reply (handles ```json fences and chatter)."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON found in reply")
    s = min(starts)
    opener = t[s]
    closer = "}" if opener == "{" else "]"
    depth, in_str, esc = 0, False, False
    for i in range(s, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(t[s:i + 1])
    raise ValueError("unterminated JSON in reply")


Validator = Callable[[object], list[str]]   # returns a list of error strings (empty = OK)


def run_pass(brain: Provider, pass_name: str, messages: list[dict], validator: Validator | None = None,
             attempts: int = 3, max_repairs: int = 3, max_tokens: int = 6000, temperature: float = 0.4):
    """Ask the brain, parse JSON, validate in code, repair. Returns the parsed object."""
    last_errors: list[str] = []
    for attempt in range(1, attempts + 1):
        convo = list(messages)
        cap = max_tokens
        for rnd in range(max_repairs + 1):
            try:
                c = brain.complete(convo, json_schema={}, max_tokens=cap, temperature=temperature,
                                   pass_name=pass_name)
            except (NeedsManual, BrainError):
                raise
            try:
                data = extract_json(c.text)
                errors = validator(data) if validator else []
            except Exception as e:  # parse failure counts as a validation error
                data, errors = None, [f"Reply was not valid JSON: {e}"]
            if not errors:
                if rnd or attempt > 1:
                    log.info(f"[brain:{pass_name}] valid after attempt {attempt}, repair {rnd}")
                return data
            last_errors = errors
            log.warning(f"[brain:{pass_name}] attempt {attempt} round {rnd}: {len(errors)} errors: {errors[:3]}")
            if rnd == max_repairs:
                break
            cap = max(500, min(int(max(c.tokens_out, len(c.text) // 4) * 1.3) + 200, max_tokens))
            convo = convo + [
                {"role": "assistant", "content": c.text},
                {"role": "user", "content": "Your JSON failed validation. Fix ONLY these errors and reply with the "
                 "complete corrected JSON, nothing else:\n- " + "\n- ".join(errors[:40])},
            ]
        log.warning(f"[brain:{pass_name}] fresh attempt after {max_repairs} failed repairs")
    raise NeedsReview(f"{pass_name}: still invalid after {attempts} attempts: {last_errors[:10]}")
