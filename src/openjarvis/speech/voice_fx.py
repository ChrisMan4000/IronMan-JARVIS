# New file for the IronMan J.A.R.V.I.S. project (see NOTICE).
"""Small stateful audio effects for streamed speech (works chunk by chunk, no clicks).

"studio": warm EQ + gentle compressor + light room echo, the "take 5" JARVIS polish
(same idea as the ffmpeg chain highpass/bass/eq/treble/acompressor/aecho/loudnorm).
"""

from __future__ import annotations

import math
from typing import Any


def _biquad(kind: str, f0: float, sr: int, gain_db: float = 0.0, q: float = 0.707):
    """RBJ cookbook biquad -> (b, a) normalized."""
    A = 10 ** (gain_db / 40)
    w = 2 * math.pi * f0 / sr
    cw, sw = math.cos(w), math.sin(w)
    alpha = sw / (2 * q)
    if kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind in ("low", "high"):
        s = 2 * math.sqrt(A) * alpha
        if kind == "low":
            b = [A * ((A + 1) - (A - 1) * cw + s), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - s)]
            a = [(A + 1) + (A - 1) * cw + s, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - s]
        else:
            b = [A * ((A + 1) + (A - 1) * cw + s), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - s)]
            a = [(A + 1) - (A - 1) * cw + s, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - s]
    else:
        raise ValueError(kind)
    return [x / a[0] for x in b], [x / a[0] for x in a]


class StudioFX:
    """Call process(chunk) for each float32 chunk in order; state carries over."""

    def __init__(self, sr: int = 24000) -> None:
        import numpy as np

        self.sr = sr
        self.filters = [
            _biquad("hp", 60, sr, q=0.707),
            _biquad("low", 150, sr, 5.0, q=0.8),
            _biquad("peak", 300, sr, 1.5, q=1.0),
            _biquad("peak", 3000, sr, -2.0, q=1.5),
            _biquad("high", 8000, sr, -2.0, q=0.707),
        ]
        self.zi = [np.zeros(2) for _ in self.filters]
        self.env = 0.0
        self.att = math.exp(-1 / (0.010 * sr))
        self.rel = math.exp(-1 / (0.150 * sr))
        self.thr = 10 ** (-20 / 20)
        self.makeup = 10 ** (2 / 20)
        self.d1, self.d2 = int(0.028 * sr), int(0.047 * sr)
        self.hist = np.zeros(self.d2, np.float32)  # last samples for the echo taps

    def process(self, x: Any) -> Any:
        import numpy as np
        from scipy.signal import lfilter

        y = np.asarray(x, dtype=np.float64)
        for i, (b, a) in enumerate(self.filters):
            y, self.zi[i] = lfilter(b, a, y, zi=self.zi[i])
        # compressor (peak envelope, ratio 3) - per-sample loop kept small with numpy blocks
        out = np.empty_like(y)
        env, att, rel, thr = self.env, self.att, self.rel, self.thr
        ay = np.abs(y)
        for n in range(len(y)):
            v = ay[n]
            env = att * env + (1 - att) * v if v > env else rel * env + (1 - rel) * v
            g = 1.0 if env <= thr else (thr * (env / thr) ** (1 / 3)) / env
            out[n] = y[n] * g
        self.env = env
        out *= self.makeup
        # light room echo (two taps), state = last d2 samples
        buf = np.concatenate([self.hist.astype(np.float64), out])
        n0 = len(self.hist)
        wet = 0.8 * out + 0.12 * buf[n0 - self.d1 : n0 - self.d1 + len(out)] + 0.08 * buf[: len(out)]
        self.hist = buf[-self.d2 :].astype(np.float32)
        wet *= 0.85 * 1.6  # out gain, then a fixed lift in place of loudnorm
        return np.clip(wet, -0.98, 0.98).astype(np.float32)
