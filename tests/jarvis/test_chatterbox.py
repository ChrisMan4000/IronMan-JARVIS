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
        "temperature": ct.TEMPERATURE,
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

def _speech(seconds, rate=24000, level=0.5):
    """Noise that stands in for speech (loud enough to never count as quiet)."""
    rng = np.random.default_rng(1)
    return (rng.uniform(-1, 1, int(seconds * rate)) * level).astype(np.float32)


def test_trim_tail_cuts_mumbling_after_the_pause():
    from openjarvis.speech import chatterbox_tts as ct

    text = "x" * 36  # 36 characters: about 2 s of speech
    wav = np.concatenate(
        [_speech(2.0), np.zeros(int(0.5 * 24000), np.float32), _speech(3.0, level=0.3)]
    )  # 5.5 s for a 2 s sentence: runaway mumbling
    out = ct.trim_tail(wav, text)
    assert 2.0 * 24000 < len(out) < 2.3 * 24000  # sentence plus a short bit of the pause
    assert abs(out[-1]) < 1e-6  # faded out, no click


def test_trim_tail_keeps_a_pause_inside_the_sentence_and_plain_endings():
    from openjarvis.speech import chatterbox_tts as ct

    text = "x" * 60  # about 4 s: a pause at 1 s is inside the sentence
    gap = np.zeros(int(0.5 * 24000), np.float32)
    inside = np.concatenate([_speech(1.0), gap, _speech(3.0)])
    assert len(ct.trim_tail(inside, text)) == len(inside)
    ending = np.concatenate([_speech(4.0), gap])  # only silence after the sentence
    assert len(ct.trim_tail(ending, text)) == len(ending)
    short = "x" * 45  # 2.5 s: a pause before the last word of a normal-length piece
    last_word = np.concatenate([_speech(2.2), np.zeros(int(0.4 * 24000), np.float32), _speech(0.4)])
    assert len(ct.trim_tail(last_word, short)) == len(last_word)

def test_marks_only_are_never_sent_to_the_model():
    from openjarvis.speech import chatterbox_tts as ct

    backend = ct.ChatterboxTTSBackend(device="cpu")
    backend._model = FakeModel()
    result = backend.synthesize("~~ ")  # a leftover prediction mark: nothing to say
    assert backend._model.calls == []
    assert result.duration_seconds == pytest.approx(0.1)
