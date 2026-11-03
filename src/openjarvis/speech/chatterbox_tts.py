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
CLIP_SUFFIXES = (".wav", ".mp3", ".flac")


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
        with self._lock:
            wav = self._ensure_model().generate(
                text,
                language_id=self._language_id,
                audio_prompt_path=clip,
                exaggeration=EXAGGERATION,
                cfg_weight=CFG_WEIGHT,
            )
        if hasattr(wav, "cpu"):  # torch tensor -> numpy
            wav = wav.cpu().numpy()
        wav = np.atleast_2d(wav)  # (channels, samples)
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

    def available_voices(self) -> list[str]:
        """Only the built-in voice has a name; any other voice is an audio clip path."""
        return ["default"]

    def health(self) -> bool:
        """True when chatterbox-tts is installed (checked without importing torch)."""
        try:
            return importlib.util.find_spec("chatterbox") is not None
        except (ImportError, ValueError):
            return False
