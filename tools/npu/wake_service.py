"""Wake-word service: listens to the microphone for "Hey Jarvis" (openWakeWord, runs on the CPU).

It serves a counter at http://127.0.0.1:8766 ({"wake_count": n, "last_wake": t}).
The HUD page reads that counter and starts listening when it goes up.

Reviewed 2026-10-14:
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

import sounddevice as sd
from openwakeword.model import Model

# Settings
PORT = 8766
THRESH = 0.5   # how sure the model must be (0 to 1)
COOL = 3.0     # seconds to wait after a wake before the next one counts
ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
ALLOWED_HOSTS = ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib",
                          "site-packages", "openwakeword", "resources", "models", "hey_jarvis_v0.1.onnx")

# Shared counter (read by the HUD)
state = {"wake_count": 0, "last_wake": 0.0}


class H(BaseHTTPRequestHandler):
    """Answers GET / with the counter as JSON."""

    def do_GET(self):
        host_ok = self.headers.get("Host", "").strip().lower() in ALLOWED_HOSTS
        origin = self.headers.get("Origin", "")
        b = json.dumps(state if host_ok else {"error": "bad host"}).encode()
        self.send_response(200 if host_ok else 403)
        self.send_header("Content-Type", "application/json")
        if host_ok and origin in ALLOWED_ORIGINS:  # only the HUD may read this from a browser
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


# Start the small web server (this PC only) in the background.
srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

# Load the "Hey Jarvis" model and listen to the default microphone.
m = Model(wakeword_models=[MODEL_PATH], inference_framework="onnx")
print("Ready. Say 'Hey Jarvis'. Ctrl+C stops. Address: http://127.0.0.1:%d" % PORT)
last = 0.0
with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1280) as s:
    while True:
        data, _ = s.read(1280)
        sc = m.predict(data[:, 0])
        v = max(sc.values())
        if v >= THRESH and time.time() - last > COOL:
            last = time.time()
            state["wake_count"] += 1
            state["last_wake"] = last
            print("WAKE", state["wake_count"], round(v, 2))
