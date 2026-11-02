# New file for the IronMan J.A.R.V.I.S. project (see NOTICE). Optional GPU voice: needs chatterbox-tts and CUDA PyTorch (tools/voice-setup.ps1 installs them).
"""Chatterbox TTS backend — Zero-shot multilingual TTS from Resemble AI.

Requires the chatterbox package: pip install chatterbox-tts
Also requires torchaudio for audio processing.
"""

from __future__ import annotations

import io
import logging
import threading
from typing import Any, Dict, List

import torchaudio
import numpy as np
import soundfile as sf
from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult

logger = logging.getLogger(__name__)

_IMPORT_LOCK = threading.RLock()


def _import_chatterbox() -> Any:
    """Import ``chatterbox``, tolerating missing installations.

    Uses ``chatterbox.mtl_tts`` for the Multilingual V3 model.
    """
    with _IMPORT_LOCK:
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            return ChatterboxMultilingualTTS
        except ImportError as exc:
            logger.error("chatterbox-tts not installed. Run: pip install chatterbox-tts")
            raise exc


@TTSRegistry.register("chatterbox")
class ChatterboxTTSBackend(TTSBackend):
    """Chatterbox TTS — Zero-shot multilingual TTS via Resemble AI models."""

    backend_id = "chatterbox"

    def __init__(
        self,
        *,
        model_path: str = "",
        device: str = "auto",
        language_id: str = "en",
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._language_id = language_id
        self._model: Any | None = None
        self._lock = threading.RLock()

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            MTL = _import_chatterbox()
            model = MTL.from_pretrained(device=(self._device if self._device in ("cuda", "cpu") else ("cuda" if __import__("torch").cuda.is_available() else "cpu")))
            self._model = model
            return model
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize Chatterbox: {exc}") from exc

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "wav",
    ) -> TTSResult:
        """Synthesize text to audio using zero-shot voice cloning or default."""
        
        # Chatterbox uses audio_prompt_path for voice cloning.
        # If voice_id is a path to a .wav, use it.
        audio_prompt = None
        if voice_id and voice_id.endswith((".wav", ".mp3", ".flac")):
            audio_prompt = voice_id

        with self._lock:
            model = self._ensure_model()

        try:
            # Chatterbox Multilingual V3 generate returns a tensor
            with self._lock:
                wav = model.generate(text, language_id=self._language_id, audio_prompt_path=audio_prompt, exaggeration=1.0, cfg_weight=0.5)
            
            # Convert tensor to numpy
            if hasattr(wav, "cpu"):
                wav = wav.cpu().numpy()
            
            # Ensure 2D array (samples, channels) for soundfile
            if wav.ndim == 1:
                wav = wav[np.newaxis, :]

            # Chatterbox typically uses 24kHz
            sr = 24000 
            
            # Convert to bytes
            buf = io.BytesIO()
            sf.write(buf, wav.T, sr, format=output_format.upper())
            audio_bytes = buf.getvalue()

            return TTSResult(
                audio=audio_bytes,
                format=output_format,
                duration_seconds=wav.shape[-1] / sr,
                voice_id=voice_id or "chatterbox-default",
                sample_rate=sr,
                metadata={"backend": "chatterbox", "lang_id": self._language_id},
            )
        except Exception as exc:
            raise RuntimeError(f"Chatterbox synthesis failed: {exc}") from exc

    def available_voices(self) -> List[str]:
        """Chatterbox is zero-shot. Returns indicator of capability."""
        return ["default", "custom_audio_file"]

    def health(self) -> bool:
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            return True
        except ImportError:
            return False
