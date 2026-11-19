# Modified for the IronMan J.A.R.V.I.S. project (see NOTICE). Original: https://github.com/open-jarvis/OpenJarvis (Apache-2.0)
"""Speech subsystem — speech-to-text and text-to-speech backends."""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

# Optional STT backends — each registers itself via @SpeechRegistry.register()
for _mod in ("faster_whisper", "openai_whisper", "deepgram"):
    try:
        importlib.import_module(f".{_mod}", __name__)
    except ImportError as _exc:
        logger.debug("Optional STT backend %s not loaded: %s", _mod, _exc)

# Optional TTS backends — each registers itself via @TTSRegistry.register()
for _mod in ("cartesia_tts", "chatterbox_tts", "elevenlabs_tts", "kokoro_tts", "openai_tts"):
    try:
        importlib.import_module(f".{_mod}", __name__)
    except ImportError as _exc:
        logger.debug("Optional TTS backend %s not loaded: %s", _mod, _exc)
