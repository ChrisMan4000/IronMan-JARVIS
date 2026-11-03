"""Wake-word service: listens for "Hey Jarvis" on the microphone (openWakeWord, CPU).

It serves a counter at http://127.0.0.1:8766 ({"wake_count": n, "last_wake": t}).
The HUD page reads that counter and starts listening when it goes up.

Security rules:
- Only the HUD page (http://localhost:5173 or http://127.0.0.1:5173) may read the
  counter from a browser; other websites get no CORS header.
- Requests with a wrong Host header are refused (stops DNS rebinding).
- The model file is found from this file's own folder, not from the current folder.
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8766
WAKE_THRESHOLD = 0.5  # how sure the model must be (0 to 1)
COOLDOWN_SECONDS = 3.0  # after a wake, the next one counts only after this pause
SAMPLE_RATE = 16000
BLOCK = 1280  # samples per prediction (80 ms)
ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
ALLOWED_HOSTS = ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)
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

# Shared counter (read by the HUD)
state = {"wake_count": 0, "last_wake": 0.0}


class CounterHandler(BaseHTTPRequestHandler):
    """Answers GET / with the counter as JSON."""

    def do_GET(self):
        host_ok = self.headers.get("Host", "").strip().lower() in ALLOWED_HOSTS
        origin = self.headers.get("Origin", "")
        body = json.dumps(state if host_ok else {"error": "bad host"}).encode()
        self.send_response(200 if host_ok else 403)
        self.send_header("Content-Type", "application/json")
        # Only the HUD may read this from a browser.
        if host_ok and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def count_wake(score, now, last_wake):
    """True when a score is a new wake: sure enough and past the cooldown."""
    return score >= WAKE_THRESHOLD and now - last_wake > COOLDOWN_SECONDS


def listen():
    """Load the "Hey Jarvis" model and count wakes from the default microphone."""
    import sounddevice as sd
    from openwakeword.model import Model

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
                state["wake_count"] += 1
                state["last_wake"] = now
                print("WAKE", state["wake_count"], round(score, 2))


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), CounterHandler)  # this PC only
    threading.Thread(target=server.serve_forever, daemon=True).start()
    listen()


if __name__ == "__main__":
    main()
