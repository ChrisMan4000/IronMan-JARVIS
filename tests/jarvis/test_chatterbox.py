"""Chatterbox voice backend: loads without torch, reports health, writes audio."""

from __future__ import annotations

import importlib
import io
import sys

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")


def test_module_loads_without_torch_or_chatterbox(monkeypatch):
    for name in ("torch", "torchaudio", "chatterbox"):
        monkeypatch.setitem(sys.modules, name, None)  # importing them now fails
    monkeypatch.delitem(sys.modules, "openjarvis.speech.chatterbox_tts", raising=False)
    module = importlib.import_module("openjarvis.speech.chatterbox_tts")
    assert module.ChatterboxTTSBackend.backend_id == "chatterbox"


def test_health_follows_the_install(monkeypatch):
    from openjarvis.speech import chatterbox_tts as ct

    monkeypatch.setattr(ct.importlib.util, "find_spec", lambda name: None)
    assert ct.ChatterboxTTSBackend().health() is False
    monkeypatch.setattr(ct.importlib.util, "find_spec", lambda name: object())
    assert ct.ChatterboxTTSBackend().health() is True


class FakeModel:
    def __init__(self):
        self.calls = []

    def generate(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return np.zeros(2400, dtype=np.float32)  # 0.1 s of silence


def test_synthesize_uses_the_clip_and_the_chosen_settings():
    from openjarvis.speech import chatterbox_tts as ct

    backend = ct.ChatterboxTTSBackend(device="cpu")
    backend._model = FakeModel()
    result = backend.synthesize("Hello sir", voice_id="C:/voices/hood2.WAV", speed=1.3)
    text, kwargs = backend._model.calls[0]
    assert text == "Hello sir"
    assert kwargs == {
        "language_id": "en",
        "audio_prompt_path": "C:/voices/hood2.WAV",
        "exaggeration": ct.EXAGGERATION,
        "cfg_weight": ct.CFG_WEIGHT,
    }
    audio, rate = sf.read(io.BytesIO(result.audio))
    assert rate == ct.SAMPLE_RATE and len(audio) == 2400
    assert result.duration_seconds == pytest.approx(0.1)


def test_a_voice_name_is_not_used_as_a_clip():
    from openjarvis.speech import chatterbox_tts as ct

    backend = ct.ChatterboxTTSBackend(device="cpu")
    backend._model = FakeModel()
    backend.synthesize("Hi", voice_id="bm_george")
    assert backend._model.calls[0][1]["audio_prompt_path"] is None
