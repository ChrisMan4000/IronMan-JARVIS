# New file for the IronMan J.A.R.V.I.S. project (see NOTICE). Optional GPU voice: needs
# chatterbox-tts and CUDA PyTorch (tools/voice-setup.ps1 installs them).
"""Chatterbox TTS backend: zero-shot multilingual speech from Resemble AI.

The voice is copied from a short audio clip: pass its path (.wav/.mp3/.flac) as
voice_id; without one the model's built-in voice is used. Chatterbox has no speed
setting, so the speed argument is accepted (the TTS interface requires it) but not
used. Heavy packages (torch, chatterbox) are imported only when speech is made.
"""

from __future__ import annotations

import importlib.util
import io
import logging
import threading
from typing import Any

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000  # Chatterbox output rate
EXAGGERATION = 1.0  # emotion strength; 1.5 added stray sounds with the cloned voice
CFG_WEIGHT = 0.5  # how closely the speech follows the voice clip
TEMPERATURE = 0.6  # lower than Chatterbox's 0.8: less made-up mumbling after the sentence
# Tail trim: Chatterbox sometimes keeps "talking" (mumbling) after the real sentence.
# After the sentence's expected length, the audio is cut at the first clear pause.
CHARS_PER_SECOND = 18.0  # speaking rate measured with the cloned voice (2026-11-04: 15-21)
TAIL_SEARCH_FROM = 1.0  # look for the pause after the expected length
RUNAWAY_FACTOR = 1.8  # only audio longer than this many times the expected length
RUNAWAY_EXTRA = 1.0  # ... plus this many seconds is trimmed (normal speech is never cut)
PAUSE_SECONDS = 0.3  # a pause at least this long counts as "sentence over"
QUIET_SHARE = 0.04  # quiet = below this share of the loudest part (per 20 ms frame)
KEEP_AFTER_PAUSE = 0.15  # seconds of the pause kept, so the last word fades naturally
FADE_SECONDS = 0.03
CLIP_SUFFIXES = (".wav", ".mp3", ".flac")


def trim_tail(samples: Any, text: str, rate: int = SAMPLE_RATE) -> Any:
    """Cut mumbling after the real sentence: the audio up to the first clear pause
    after the sentence's expected length (1-D numpy samples in, a shorter copy or the
    same array out). Nothing is cut when no such pause exists."""
    import numpy as np

    frame = max(1, int(rate * 0.02))
    n = len(samples) // frame
    if n < 3:
        return samples
    rms = np.sqrt(np.mean(np.square(samples[: n * frame].reshape(n, frame)), axis=1))
    quiet = rms < rms.max() * QUIET_SHARE
    expected = len(text) / CHARS_PER_SECOND
    if len(samples) / rate < expected * RUNAWAY_FACTOR + RUNAWAY_EXTRA:
        return samples  # normal length: keep every word
    start = int(expected * TAIL_SEARCH_FROM / 0.02)
    need = max(1, int(PAUSE_SECONDS / 0.02))
    run = 0
    for i in range(start, n):
        run = run + 1 if quiet[i] else 0
        if run < need:
            continue
        pause_start = i - need + 1
        if not (~quiet[i + 1 :]).any():
            return samples  # only silence follows: nothing to cut
        cut = (pause_start + int(KEEP_AFTER_PAUSE / 0.02)) * frame
        out = samples[:cut].copy()
        fade = min(len(out), int(rate * FADE_SECONDS))
        out[len(out) - fade :] *= np.linspace(1.0, 0.0, fade, dtype=out.dtype)
        logger.info(
            "Chatterbox: cut %.2f s of mumbling after %r",
            (len(samples) - cut) / rate,
            text[-40:],
        )
        return out
    return samples


@TTSRegistry.register("chatterbox")
class ChatterboxTTSBackend(TTSBackend):
    """Chatterbox TTS: zero-shot multilingual TTS via Resemble AI models."""

    backend_id = "chatterbox"

    def __init__(
        self, *, model_path: str = "", device: str = "auto", language_id: str = "en"
    ) -> None:
        # model_path is accepted so existing configs still work;
        # the weights always come from Hugging Face.
        del model_path
        self._device = device
        self._language_id = language_id
        self._model: Any | None = None
        self._lock = (
            threading.Lock()
        )  # one GPU model: load and generate one request at a time

    def _pick_device(self) -> str:
        if self._device in ("cuda", "cpu"):
            return self._device
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _ensure_model(self) -> Any:
        """Load the model once (call with self._lock held)."""
        if self._model is None:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            try:
                self._model = ChatterboxMultilingualTTS.from_pretrained(
                    device=self._pick_device()
                )
            except Exception as exc:  # download, CUDA or memory problems
                raise RuntimeError(f"Failed to initialize Chatterbox: {exc}") from exc
        return self._model

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "wav",
    ) -> TTSResult:
        """Speak text in the voice of the voice_id clip (or the default voice)."""
        import numpy as np
        import soundfile as sf

        if speed != 1.0:
            logger.debug("Chatterbox has no speed setting; speaking at normal speed")
        clip = voice_id if voice_id.lower().endswith(CLIP_SUFFIXES) else None
        if not any(c.isalnum() for c in text):
            # nothing to say (only marks such as "~~"): Chatterbox would mumble for seconds
            wav = np.zeros(int(SAMPLE_RATE * 0.1), np.float32)
        else:
            wav = self._generate(text, clip)
        if hasattr(wav, "cpu"):  # torch tensor -> numpy
            wav = wav.cpu().numpy()
        wav = np.atleast_2d(wav)  # (channels, samples)
        wav = np.atleast_2d(trim_tail(wav[0], text))  # Chatterbox speaks mono
        buf = io.BytesIO()
        sf.write(buf, wav.T, SAMPLE_RATE, format=output_format.upper())
        return TTSResult(
            audio=buf.getvalue(),
            format=output_format,
            duration_seconds=wav.shape[-1] / SAMPLE_RATE,
            voice_id=voice_id or "default",
            sample_rate=SAMPLE_RATE,
            metadata={"backend": "chatterbox", "lang_id": self._language_id},
        )

    def _generate(self, text: str, clip: str | None) -> Any:
        """One Chatterbox call (one request at a time on the GPU)."""
        with self._lock:
            return self._ensure_model().generate(
                text,
                language_id=self._language_id,
                audio_prompt_path=clip,
                exaggeration=EXAGGERATION,
                cfg_weight=CFG_WEIGHT,
                temperature=TEMPERATURE,
            )

    def available_voices(self) -> list[str]:
        """Only the built-in voice has a name; any other voice is an audio clip path."""
        return ["default"]

    def health(self) -> bool:
        """True when chatterbox-tts is installed (checked without importing torch)."""
        try:
            return importlib.util.find_spec("chatterbox") is not None
        except (ImportError, ValueError):
            return False
