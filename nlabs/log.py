# log.py — console + file logging and stage timers.
# Every station logs through `get_logger()`; `attach_run_log()` adds work/<run>/run.log.
# `stage()` is a context manager that prints a banner and the elapsed time.
from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from pathlib import Path

_LOG = logging.getLogger("nlabs")
if not _LOG.handlers:
    _LOG.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%H:%M:%S"))
    _LOG.addHandler(h)

SECRET_HINTS = ("key", "token", "secret", "authorization")


def get_logger() -> logging.Logger:
    return _LOG


def attach_run_log(path: Path):
    for h in list(_LOG.handlers):
        if isinstance(h, logging.FileHandler):
            _LOG.removeHandler(h)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s"))
    _LOG.addHandler(fh)


def redact(text: str, secrets: list[str]) -> str:
    """Never let API keys reach logs."""
    for s in secrets:
        if s and len(s) > 6:
            text = text.replace(s, s[:3] + "***")
    return text


TIMINGS: dict[str, float] = {}


@contextmanager
def stage(name: str):
    _LOG.info("=" * 8 + f" STATION: {name} " + "=" * 8)
    t0 = time.time()
    try:
        yield
    finally:
        dt = time.time() - t0
        TIMINGS[name] = TIMINGS.get(name, 0) + dt
        _LOG.info(f"[{name}] finished in {dt:.1f}s")


def progress(i: int, n: int, label: str = "", t0: float | None = None):
    """Simple progress line with ETA (no extra dependency)."""
    pct = 100.0 * i / max(n, 1)
    eta = ""
    if t0 and i:
        rem = (time.time() - t0) / i * (n - i)
        eta = f" ETA {rem:5.0f}s"
    bar = "#" * int(pct / 5)
    sys.stdout.write(f"\r  {label:<14} [{bar:<20}] {i}/{n}{eta}   ")
    sys.stdout.flush()
    if i >= n:
        sys.stdout.write("\n")
