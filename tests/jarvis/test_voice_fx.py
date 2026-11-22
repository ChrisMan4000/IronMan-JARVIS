"""Studio voice effect: filter maths and chunk-by-chunk processing."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from openjarvis.speech.voice_fx import StudioFX, _biquad  # noqa: E402

SR = 24000


@pytest.mark.parametrize("kind", ["hp", "peak", "low", "high"])
def test_biquad_is_normalised(kind):
    b, a = _biquad(kind, 1000, SR, gain_db=3.0)
    assert len(b) == 3 and len(a) == 3
    assert a[0] == pytest.approx(1.0)


def test_biquad_rejects_unknown_kind():
    with pytest.raises(ValueError):
        _biquad("notch", 1000, SR)


def test_silence_stays_silent():
    out = StudioFX(SR).process(np.zeros(2400, dtype=np.float32))
    assert out.dtype == np.float32
    assert float(np.abs(out).max()) == pytest.approx(0.0, abs=1e-6)


def test_output_is_clipped_and_same_length():
    loud = np.full(4800, 5.0, dtype=np.float32)
    out = StudioFX(SR).process(loud)
    assert len(out) == len(loud)
    assert float(np.abs(out).max()) <= 0.9801


def test_chunked_equals_whole():
    t = np.arange(4800) / SR
    tone = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    whole = StudioFX(SR).process(tone)
    fx = StudioFX(SR)
    parts = np.concatenate([fx.process(tone[:1700]), fx.process(tone[1700:])])
    assert np.allclose(whole, parts, atol=1e-4)
