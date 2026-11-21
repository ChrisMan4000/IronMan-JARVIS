# New file for the IronMan J.A.R.V.I.S. project (see NOTICE). Optional GPU voice: needs
# chatterbox-tts and CUDA PyTorch (tools/voice-setup.ps1 installs them).
"""Chatterbox TTS backend: zero-shot multilingual speech from Resemble AI.

The voice is copied from a short audio clip: pass its path (.wav/.mp3/.flac) as
voice_id; without one the model's built-in voice is used. Chatterbox has no speed
setting; speed (speaking pace) is applied afterwards with a pitch-keeping time
stretch. stream() sends sound while it is still being made. Heavy packages (torch, chatterbox) are imported only when speech is made.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
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


VOICES_DIR = os.path.join(os.path.expanduser("~"), ".openjarvis", "voices")
HUD_SETTINGS = os.path.join(os.path.expanduser("~"), ".openjarvis", "hud-settings.json")
T3_FILES = {"v2": "t3_mtl23ls_v2.safetensors", "v3": "t3_mtl23ls_v3.safetensors"}
TOKENS_PER_SECOND = 25  # Chatterbox speech tokens per second of audio
FIRST_CHUNK_TOKENS = 18  # first streamed piece (~0.7 s of speech) -> fast first sound
NEXT_CHUNK_TOKENS = 35  # later pieces
HOLDBACK_TOKENS = 3  # newest tokens are decoded again next round (sound settles)
XFADE = 240  # samples (10 ms) blended between rounds
CONTEXT_TOKENS = 25  # tokens already sent that are decoded again as context (not all of them)
SAMPLES_PER_TOKEN = SAMPLE_RATE // TOKENS_PER_SECOND


def hud_settings() -> dict:
    """Settings saved by the HUD settings panel (empty dict if none)."""
    try:
        with open(HUD_SETTINGS, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def voice_fx_name(clip: str | None) -> str:
    """'studio' when <clip>.json next to the clip says so."""
    if not clip:
        return ""
    try:
        with open(os.path.splitext(clip)[0] + ".json", encoding="utf-8") as f:
            return str(json.load(f).get("fx", ""))
    except (OSError, ValueError):
        return ""


class _StopGen(Exception):
    pass


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
        self._t3_version = ""
        self._kind = ""  # "mtl" (Multilingual V2/V3) or "turbo" (Turbo 350M, English only)
        self._turbo: Any | None = None
        self._turbo_conds: Any | None = None
        self._default_conds: Any | None = None
        self._cond_key: tuple | None = None
        self._lock = (
            threading.Lock()
        )  # one GPU model: load and generate one request at a time

    def _pick_device(self) -> str:
        if self._device in ("cuda", "cpu"):
            return self._device
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _ensure_model(self) -> Any:
        """Load the model once (call with self._lock held); then the T3 version
        from the HUD settings (default v3, Multilingual V3 weights; "turbo" = Turbo 350M).
        Only one of the two models stays in graphics memory."""
        want = str(hud_settings().get("tts_model", "v3")).lower()
        if want == "turbo":
            return self._ensure_turbo()
        if self._turbo is not None:
            self._turbo = self._turbo_conds = None
            _free_gpu()
        self._kind = "mtl"
        if self._model is None:
            import copy

            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            try:
                self._model = ChatterboxMultilingualTTS.from_pretrained(
                    device=self._pick_device()
                )
            except Exception as exc:  # download, CUDA or memory problems
                raise RuntimeError(f"Failed to initialize Chatterbox: {exc}") from exc
            self._default_conds = copy.deepcopy(self._model.conds)
            self._t3_version = "v2"
        if want in T3_FILES and want != self._t3_version:
            try:
                from huggingface_hub import hf_hub_download
                from safetensors.torch import load_file

                sd = load_file(hf_hub_download("ResembleAI/chatterbox", T3_FILES[want]))
                if "model" in sd:
                    sd = sd["model"][0]
                self._model.t3.load_state_dict(sd)
                self._model.t3.to(self._model.device).eval()
                self._t3_version = want
                logger.info("Chatterbox: Multilingual %s weights loaded", want.upper())
            except Exception:
                logger.exception("Chatterbox: could not load %s, keeping %s", want, self._t3_version)
        return self._model

    def _ensure_turbo(self) -> Any:
        """Chatterbox Turbo (350M, English only, lighter and faster)."""
        self._kind = "turbo"
        if self._model is not None:
            self._model = self._default_conds = None
            self._t3_version = ""
            _free_gpu()
        if self._turbo is None:
            import copy

            from chatterbox.tts_turbo import ChatterboxTurboTTS

            try:
                self._turbo = ChatterboxTurboTTS.from_pretrained(device=self._pick_device())
            except Exception as exc:  # download, CUDA or memory problems
                raise RuntimeError(f"Failed to initialize Chatterbox Turbo: {exc}") from exc
            self._turbo_conds = copy.deepcopy(self._turbo.conds)
            self._cond_key = None
            logger.info("Chatterbox: Turbo loaded")
        return self._turbo

    def _turbo_wav(self, model: Any, text: str, temperature: float) -> Any:
        """Whole sentence with Turbo (it has no token-by-token streaming here)."""
        import numpy as np

        wav = model.generate(text, temperature=temperature)
        if hasattr(wav, "cpu"):
            wav = wav.cpu().numpy()
        return trim_tail(np.atleast_2d(wav)[0], text)

    # ---------- settings per request ----------
    def _params(self, exaggeration, temperature, language_id) -> tuple[float, float, str]:
        s = hud_settings()
        ex = exaggeration if exaggeration is not None else s.get("exaggeration", EXAGGERATION)
        te = temperature if temperature is not None else s.get("temperature", TEMPERATURE)
        lang = (language_id or s.get("tts_language") or self._language_id or "en").lower()
        if lang == "auto":
            lang = self._language_id or "en"
        try:
            from chatterbox.mtl_tts import SUPPORTED_LANGUAGES

            if lang not in SUPPORTED_LANGUAGES:  # Chatterbox cannot speak it: English voice
                lang = "en"
        except ImportError:
            pass
        ex = min(2.0, max(0.25, float(ex)))
        te = min(1.5, max(0.05, float(te)))
        return ex, te, lang

    def _prep(self, model: Any, clip: str | None, exaggeration: float) -> None:
        """Voice conditionals, cached per (clip, file time)."""
        key = (self._kind, clip, os.path.getmtime(clip) if clip and os.path.exists(clip) else 0)
        if key != self._cond_key:
            if clip and self._kind == "turbo":
                # Turbo's loudness step returns float64, which its tokenizer rejects (chatterbox-tts 0.1.7)
                model.prepare_conditionals(clip, exaggeration=exaggeration, norm_loudness=False)
            elif clip:
                model.prepare_conditionals(clip, exaggeration=exaggeration)
            else:
                import copy

                model.conds = copy.deepcopy(self._turbo_conds if self._kind == "turbo" else self._default_conds)
            self._cond_key = key
        if self._kind == "turbo":  # Turbo ignores exaggeration
            return
        import torch
        from chatterbox.models.t3.modules.cond_enc import T3Cond

        c = model.conds.t3
        if float(exaggeration) != float(c.emotion_adv[0, 0, 0].item()):
            model.conds.t3 = T3Cond(
                speaker_emb=c.speaker_emb,
                cond_prompt_speech_tokens=c.cond_prompt_speech_tokens,
                emotion_adv=exaggeration * torch.ones(1, 1, 1),
            ).to(device=model.device)

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "wav",
        exaggeration: float | None = None,
        temperature: float | None = None,
        language_id: str | None = None,
    ) -> TTSResult:
        """Speak text in the voice of the voice_id clip (or the default voice)."""
        import numpy as np
        import soundfile as sf

        clip = voice_id if voice_id.lower().endswith(CLIP_SUFFIXES) else None
        ex, te, lang = self._params(exaggeration, temperature, language_id)
        if not any(c.isalnum() for c in text):
            # nothing to say (only marks such as "~~"): Chatterbox would mumble for seconds
            wav = np.zeros(int(SAMPLE_RATE * 0.1), np.float32)
        else:
            with self._lock:
                model = self._ensure_model()
                self._prep(model, clip, ex)
                if self._kind == "turbo":
                    wav, lang = self._turbo_wav(model, text, te), "en"
                else:
                    wav = model.generate(
                        text, language_id=lang, audio_prompt_path=None,
                        exaggeration=ex, cfg_weight=CFG_WEIGHT, temperature=te,
                    )
        if hasattr(wav, "cpu"):  # torch tensor -> numpy
            wav = wav.cpu().numpy()
        wav = np.atleast_2d(wav)  # (channels, samples)
        mono = trim_tail(wav[0], text)
        if voice_fx_name(clip) == "studio":
            from openjarvis.speech.voice_fx import StudioFX

            mono = StudioFX(SAMPLE_RATE).process(mono)
        mono = _pace(mono, speed)
        wav = np.atleast_2d(mono)
        buf = io.BytesIO()
        sf.write(buf, wav.T, SAMPLE_RATE, format=output_format.upper())
        return TTSResult(
            audio=buf.getvalue(),
            format=output_format,
            duration_seconds=wav.shape[-1] / SAMPLE_RATE,
            voice_id=voice_id or "default",
            sample_rate=SAMPLE_RATE,
            metadata={"backend": "chatterbox", "lang_id": lang, "t3": self._t3_version},
        )

    def stream(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        exaggeration: float | None = None,
        temperature: float | None = None,
        language_id: str | None = None,
    ):
        """Yield 16-bit mono PCM bytes (24 kHz) while the speech is still being made.

        The T3 model makes speech tokens one by one; a hook on its token embedding
        catches each new token. Every ~1 s of tokens is turned into sound by S3Gen
        (all tokens so far, so the sound stays smooth) and the new part is sent.
        """
        import queue

        import numpy as np
        import torch
        import torch.nn.functional as F
        from chatterbox.mtl_tts import punc_norm

        clip = voice_id if voice_id.lower().endswith(CLIP_SUFFIXES) else None
        ex, te, lang = self._params(exaggeration, temperature, language_id)
        if not any(c.isalnum() for c in text):
            yield np.zeros(int(SAMPLE_RATE * 0.1), np.int16).tobytes()
            return
        fx = None
        if voice_fx_name(clip) == "studio":
            from openjarvis.speech.voice_fx import StudioFX

            fx = StudioFX(SAMPLE_RATE)
        max_tokens = int((len(text) / CHARS_PER_SECOND * RUNAWAY_FACTOR + RUNAWAY_EXTRA + 1) * TOKENS_PER_SECOND)

        with self._lock:
            model = self._ensure_model()
            self._prep(model, clip, ex)
            if self._kind == "turbo":  # Turbo: whole piece at once (still fast)
                out = self._turbo_wav(model, text, te)
                if fx is not None:
                    out = fx.process(out)
                out = _pace(out, speed)
                yield (np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes()
                return
            t3 = model.t3
            stop_id = t3.hp.stop_speech_token
            valid_max = t3.hp.start_speech_token  # tokens below this are real speech tokens
            q: "queue.Queue" = queue.Queue()
            count = [0]
            abort = [False]

            def hook(_mod, inputs):
                ids = inputs[0]
                if ids.dim() == 2 and ids.shape == (1, 1):
                    tok = int(ids.item())
                    if tok < valid_max:
                        q.put(tok)
                        count[0] += 1
                        if count[0] > max_tokens or abort[0]:
                            raise _StopGen()

            def run():
                try:
                    with torch.inference_mode():
                        tt = model.tokenizer.text_to_tokens(punc_norm(text), language_id=lang).to(model.device)
                        tt = torch.cat([tt, tt], dim=0)
                        tt = F.pad(tt, (1, 0), value=t3.hp.start_text_token)
                        tt = F.pad(tt, (0, 1), value=t3.hp.stop_text_token)
                        t3.inference(
                            t3_cond=model.conds.t3, text_tokens=tt, max_new_tokens=1000,
                            temperature=te, cfg_weight=CFG_WEIGHT,
                            repetition_penalty=2.0, min_p=0.05, top_p=1.0,
                        )
                except _StopGen:
                    logger.info("Chatterbox stream: stopped long tail after %d tokens", count[0])
                except Exception:
                    logger.exception("Chatterbox stream: token generation failed")
                finally:
                    q.put(None)

            h = t3.speech_emb.register_forward_pre_hook(hook)
            th = threading.Thread(target=run, daemon=True)
            th.start()
            toks: list[int] = []
            sent = 0  # samples already sent
            tail = None  # last decode's samples [sent, sent+XFADE) for blending
            done = False
            need = FIRST_CHUNK_TOKENS
            try:
                while not done:
                    while len(toks) < need:
                        t = q.get()
                        if t is None:
                            done = True
                            break
                        toks.append(t)
                    if not toks:
                        break
                    with torch.inference_mode():
                        ws = max(0, sent // SAMPLES_PER_TOKEN - CONTEXT_TOKENS)  # window start (token)
                        st = torch.tensor(toks[ws:], dtype=torch.long, device=model.device)
                        wav, _ = model.s3gen.inference(speech_tokens=st, ref_dict=model.conds.gen)
                    wav = np.concatenate([np.zeros(ws * SAMPLES_PER_TOKEN, np.float32), wav.squeeze(0).float().cpu().numpy()])
                    end = len(wav) if done else max(sent, len(wav) - HOLDBACK_TOKENS * (SAMPLE_RATE // TOKENS_PER_SECOND))
                    if end - sent <= XFADE and not done:
                        need = len(toks) + NEXT_CHUNK_TOKENS
                        continue
                    piece = wav[sent:end].copy()
                    if tail is not None and len(piece) >= XFADE:
                        r = np.linspace(0.0, 1.0, XFADE, dtype=np.float32)
                        piece[:XFADE] = tail * (1 - r) + piece[:XFADE] * r
                    if done:
                        out, tail = piece, None
                        fade = min(len(out), int(SAMPLE_RATE * FADE_SECONDS))
                        if fade:
                            out[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
                    else:
                        out, tail = piece[:-XFADE], piece[-XFADE:].copy()
                    sent = end - (0 if done else XFADE)
                    try:  # Resemble's inaudible watermark, as model.generate() adds it
                        out = np.asarray(model.watermarker.apply_watermark(out, sample_rate=SAMPLE_RATE), np.float32)
                    except Exception:
                        logger.debug("Chatterbox stream: watermark skipped", exc_info=True)
                    if fx is not None:
                        out = fx.process(out)
                    out = _pace(out, speed)
                    yield (np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes()
                    need = len(toks) + NEXT_CHUNK_TOKENS
            finally:
                abort[0] = True
                h.remove()
                th.join(timeout=30)

    def available_voices(self) -> list[str]:
        """Built-in voice plus every clip in ~/.openjarvis/voices."""
        out = ["default"]
        try:
            out += sorted(os.path.splitext(n)[0] for n in os.listdir(VOICES_DIR) if n.lower().endswith(CLIP_SUFFIXES))
        except OSError:
            pass
        return out

    def health(self) -> bool:
        """True when chatterbox-tts is installed (checked without importing torch)."""
        try:
            return importlib.util.find_spec("chatterbox") is not None
        except (ImportError, ValueError):
            return False


def _free_gpu() -> None:
    """Give graphics memory back after a model was dropped."""
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _pace(samples: Any, speed: float) -> Any:
    """Speaking pace (0.7-1.3) without changing the pitch; 1.0 = untouched."""
    try:
        speed = float(speed or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    if abs(speed - 1.0) < 0.02 or len(samples) < 2048:
        return samples
    import librosa

    return librosa.effects.time_stretch(samples.astype("float32"), rate=min(1.3, max(0.7, speed)))
