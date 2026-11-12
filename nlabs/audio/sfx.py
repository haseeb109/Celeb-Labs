# audio/sfx.py — sound effects synthesized with numpy (no downloaded SFX needed):
# whoosh (chapter cards/transitions), boom (stamps), typewriter ticks (quote cards), clock tick.
# All return float32 stereo arrays at 48 kHz.
import numpy as np

from ..constants import AUDIO_RATE as SR


def _st(x):
    return np.stack([x, x], 1).astype(np.float32)


def whoosh(d=0.7, seed=1):
    n = int(d * SR)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    # sweep a simple one-pole low-pass cutoff up then down
    t = np.linspace(0, 1, n)
    cut = 0.02 + 0.35 * np.sin(np.pi * t) ** 2
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        acc += cut[i] * (noise[i] - acc)
        y[i] = acc
    env = np.sin(np.pi * t) ** 1.5
    return _st(y * env * 0.5)


def boom(d=1.2):
    n = int(d * SR)
    t = np.arange(n) / SR
    f = 55 * np.exp(-t * 2.5) + 30
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t * 3.2)
    y += np.random.default_rng(3).standard_normal(n) * np.exp(-t * 30) * 0.3
    return _st(y * 0.8)


def tick(d=0.035, freq=2400, seed=0):
    n = int(d * SR)
    t = np.arange(n) / SR
    y = np.random.default_rng(seed).standard_normal(n) * np.exp(-t * 200) * 0.4 + np.sin(2 * np.pi * freq * t) * np.exp(-t * 150) * 0.3
    return _st(y)


def typewriter(d=2.0, rate=11):
    out = np.zeros((int(d * SR), 2), np.float32)
    rng = np.random.default_rng(7)
    t = 0.0
    while t < d - 0.05:
        k = tick(0.03, 1800 + rng.integers(0, 900), int(t * 1000))
        i = int(t * SR)
        out[i:i + len(k)] += k[: len(out) - i] * 0.6
        t += 1 / rate * rng.uniform(0.6, 1.4)
    return out


def clock(d=2.0):
    out = np.zeros((int(d * SR), 2), np.float32)
    for k in range(int(d)):
        tk = tick(0.04, 1200 if k % 2 else 900, k)
        i = int(k * SR)
        out[i:i + len(tk)] += tk[: len(out) - i]
    return out
