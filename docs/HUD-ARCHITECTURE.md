# J.A.R.V.I.S. HUD (IronMan-JARVIS) – Technical Architecture

**HUD version:** shown in the browser tab and in the CORE STATUS panel (kept in `frontend/public/hud-version.js`).
This document describes the HUD and the programs around it. The general OpenJarvis engine is documented upstream in `docs/architecture/` (overview, engine, agents, memory, security, query flow).

## 1. In three sentences
The HUD is one full-screen web page (`hud.html`, vanilla JavaScript drawing on a canvas, plus a WebGL brain) served by a small Vite web server on port 5173, which reads live numbers from a Python helper and talks to the OpenJarvis Python server (FastAPI) that sends questions to a local language model in LM Studio. Speech comes in through a local wake-word service and faster-whisper and goes out through Kokoro or Chatterbox voices, all on your own PC. PowerShell scripts start and stop every service in order, and an Inno Setup installer sets it all up.

## 2. Technologies
| Part | Technology | Where |
|---|---|---|
| HUD page | HTML + vanilla JavaScript, Canvas 2D, WebGL (three.js, local copy), no framework | `frontend/public/hud.html`, `hud-*.js`, `vendor/three`, `vendor/world-atlas` |
| Web server for the HUD | Vite (Node.js); the main React 19 + TypeScript + Tailwind app and PWA live in the same project | `frontend/` |
| Jarvis server | Python 3.10+, FastAPI, OpenAI-compatible `/v1` API, started with `uv` | `src/openjarvis/` (`server/`, `engine/`, `agents/`, `memory/`, `speech/`, …) |
| Language model | LM Studio (local), model, context size and reasoning are switched inside the HUD | port 1234 |
| Helper (live numbers) | Python: CPU, network, GPU (nvidia-smi), fans, connections + location, CO2, loaded model, tool lights, benchmark | `tools/hwstats.py`, `tools/helper_*.py` |
| Wake word | Python service in its own virtual environment (only if set up) | `tools/npu/wake_service.py` |
| Voice | faster-whisper (listening); Kokoro or Chatterbox (speaking), chosen by the installer | `src/openjarvis/speech/`, `tools/voice-setup.ps1` |
| LAN gateway (optional) | Python HTTPS + password proxy for phone / second PC | `tools/gateway.py` |
| Performance core (optional) | Rust workspace | `rust/` |
| Automation | PowerShell: start, stop, install, uninstall, services | `start-jarvis.ps1`, `tools/services.ps1`, `tools/stop-jarvis.ps1`, `install-jarvis.ps1` |
| Installer | Inno Setup | `installer/ironman-jarvis.iss` |

## 3. Processes and ports (all on 127.0.0.1 unless noted)
| Port | Program | Started by |
|---|---|---|
| 1234 | LM Studio (model engine) | `start-jarvis.ps1` (step 1–2) |
| 8000 | Jarvis server (FastAPI) | `start-jarvis.ps1` (own terminal tab) |
| 5173 | HUD web server (Vite) | `tools/services.ps1` |
| 8765 | helper (live numbers) | `tools/services.ps1` |
| 8766 | wake-word service | `tools/services.ps1` (only if set up) |
| 8443 | LAN gateway (HTTPS + password, 0.0.0.0) | only after `tools/setup-remote-access.ps1` |

Start order: LM Studio → model → backup watcher, helper, wake word, server → HUD → browser. The **Jarvis** desktop icon starts everything, **Stop Jarvis** (`tools/stop-jarvis.ps1`) stops it all.

## 4. The HUD page
* `hud.html` draws every panel on one canvas each frame (`box()`, `tx()` helpers, one unit `u` scales everything to the screen, 5120×1440 down to phones).
* `hud-shared.js` – shared layout and hand-over object `window.JarvisHud` (panels, wings, map area, captured texts, brain, hooks `onAsk` / `onLogLine`).
* `hud-boot-scene.js`, `hud-boot.js` – cinematic intro: pieces fly in, texts of the first frame are captured and replayed, panels unroll, then fade-out (about 6 s, click skips).
* `hud-brain.js` - the living vortex brain in the centre (WebGL feedback effect in the style of the Geiss music visualiser: a voice wave, a beating two-lobed core and nerve fibres, pulled inward like a tunnel and pushed outward while Jarvis speaks; 120 steps per second; the intro builds it from single pixels sucked in from the whole screen; replaces the centre ring).
* World map ("NETWORK TRAFFIC // WORLD"): land from `vendor/world-atlas/land-110m.json` sampled into dots; connections come from the helper (`netstat` → public IPs → offline DB-IP database `tools/dbip.mmdb`); home point from `hud-home.js` (`HOME_CFG`, written by `tools/set-home-city.ps1`).
* `hud-local.js` – private extension hooks of this PC (not part of the public project). `hud-version.js` – version number.
* Data in: helper `GET http://127.0.0.1:8765/` (every ~0.8 s), server `/v1` (chat, streaming), weather (Open-Meteo), CO2 (NOAA).

## 5. Question flow
Voice (wake word or F6) → faster-whisper → text → HUD → Jarvis server `/v1` → agent (memory, optional tools: web search via Firecrawl, news, documents via Big RAG, Hue, Tado) → LM Studio model → streamed answer → HUD (confidence, sources as links, tool lights) → Kokoro/Chatterbox voice.

## 6. Security and privacy
* All Jarvis ports listen on `127.0.0.1` only; the optional gateway (8443) adds HTTPS and a password and is the trust boundary for the LAN.
* `code_interpreter`, `file_read`, `shell_exec` are off by default; upstream analytics are off.
* Internet use: weather, CO2, one-time downloads (models, wake word, location database) and only if enabled: web search, news feeds, Hue bridge, Tado.
* Secrets (`hue-key.txt`, `tado-token.json`, Firecrawl key, gateway password) stay on the PC and are never shared.

## 7. Versioning and history
`frontend/public/hud-version.js` → `window.HUD_VERSION`. Change it there only. The number after the dot counts the iterations: add 1 with every commit that changes the HUD files (`hud.html`, `hud-*.js`, `hud.webmanifest`).
| Version | Date | Changes |
|---|---|---|
| v1.00 | 2026-11-06 | first numbered release of the HUD: version shown in tab and CORE STATUS; this document |
| v1.43 | 2026-11-06 | the number after the dot now counts the iterations (git commits that changed the HUD files; 42 before this one); the private home world page has its own number |
