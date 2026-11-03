"""Wake-word service: listens for "Hey Jarvis" on the microphone (openWakeWord, CPU).

It serves a counter at http://127.0.0.1:8766 ({"wake_count": n, "last_wake": t}).
The HUD page reads that counter and starts listening when it goes up.

Security rules:
- Only the HUD page (http://localhost:5173 or http://127.0.0.1:5173) may read the
  counter from a browser; other websites get no CORS header.
- Requests with a wrong Host header are refused (stops DNS rebinding).
- The model file is found from this file's own folder, not from the current folder.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType
from typing import Any

try:  # only in this folder's .venv; the tests import this file without them
    import sounddevice as sd
    from openwakeword.model import Model
except ImportError:
    sd = Model = None

logger = logging.getLogger(__name__)


def _load_helper_http() -> ModuleType:
    """tools\\helper_http.py, loaded by its path: this service runs in its own venv
    (tools\\npu\\.venv) where the tools folder is not importable. Stdlib only."""
    tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "jarvis_helper_http", os.path.join(tools, "helper_http.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("tools\\helper_http.py not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_helper_http = _load_helper_http()
ALLOWED_ORIGINS = _helper_http.ALLOWED_ORIGINS  # the HUD page, same rule as the helper

PORT = 8766
WAKE_THRESHOLD = 0.5  # how sure the model must be (0 to 1)
COOLDOWN_SECONDS = 3.0  # after a wake, the next one counts only after this pause
SAMPLE_RATE = 16000
BLOCK = 1280  # samples per prediction (80 ms)
WAKE_HOSTS = _helper_http.local_hosts(PORT)
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".venv",
    "Lib",
    "site-packages",
    "openwakeword",
    "resources",
    "models",
    "hey_jarvis_v0.1.onnx",
)


class WakeCounter:
    """How often "Hey Jarvis" was heard; written by the listener, read by HTTP."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.wake_count = 0
        self.last_wake = 0.0

    def add(self, now: float) -> int:
        with self._lock:
            self.wake_count += 1
            self.last_wake = now
            return self.wake_count

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"wake_count": self.wake_count, "last_wake": self.last_wake}


counter = WakeCounter()


class CounterHandler(BaseHTTPRequestHandler):
    """Answers GET / with the counter as JSON."""

    def do_GET(self) -> None:
        host_ok = self.headers.get("Host", "").strip().lower() in WAKE_HOSTS
        origin = self.headers.get("Origin", "")
        answer = counter.snapshot() if host_ok else {"error": "bad host"}
        body = json.dumps(answer).encode()
        self.send_response(200 if host_ok else 403)
        self.send_header("Content-Type", "application/json")
        # Only the HUD may read this from a browser.
        if host_ok and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - base name
        """Requests go to the debug log instead of the console."""
        logger.debug("%s " + format, self.address_string(), *args)


def count_wake(score: float, now: float, last_wake: float) -> bool:
    """True when a score is a new wake: sure enough and past the cooldown."""
    return score >= WAKE_THRESHOLD and now - last_wake > COOLDOWN_SECONDS


def listen() -> None:
    """Load the "Hey Jarvis" model and count wakes from the default microphone."""
    if sd is None or Model is None:
        raise RuntimeError("needs tools\\npu\\.venv (sounddevice, openwakeword)")
    model = Model(wakeword_models=[MODEL_PATH], inference_framework="onnx")
    print("Ready. Say 'Hey Jarvis'. Ctrl+C stops. Address: http://127.0.0.1:%d" % PORT)
    last_wake = 0.0
    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=BLOCK
    ) as mic:
        while True:
            data, _overflow = mic.read(BLOCK)
            score = max(model.predict(data[:, 0]).values())
            now = time.time()
            if count_wake(score, now, last_wake):
                last_wake = now
                print("WAKE", counter.add(now), round(score, 2))


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), CounterHandler)  # this PC only
    threading.Thread(target=server.serve_forever, daemon=True).start()
    listen()


if __name__ == "__main__":
    main()
