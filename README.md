# IronMan J.A.R.V.I.S. – An IronMan-Style Web-Interface with all the Bells & Whistles

*Tony Stark had a billion dollars and a genius brain. I had a free Claude web chat and 36 hours.*

![The IronMan J.A.R.V.I.S. HUD](docs/images/hud-screenshot.png)
<sub>The HUD at 5120x1440. Click the image to see it full size.</sub>

![The same HUD, with an orange box on every panel telling you where its data comes from](docs/images/hud-annotated.png)
<sub>Every orange box says where that panel gets its data. The full list is further down.</sub>

> **Credit where it is due:** this is a **fork of [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)** (Apache-2.0). The brain, the server and the engine are theirs. I added the full-screen HUD, voice, smart-home tools and installer on top. Please go give the original project a star. The original README is in [docs/OPENJARVIS-README.md](docs/OPENJARVIS-README.md).

## The honest part

- I am **not a developer**. This is my **first GitHub project**.
- It took **36 hours**, built entirely in the **free Claude web chat** (so: lots of patience, very small steps).
- It runs great on my PC. On yours? I am as curious as you are. The installer has **not** been tested on a freshly wiped PC.
- Be nice. Open an issue if something breaks and tell me what you saw.

## What you get

- **Full-screen HUD** with live GPU/CPU gauges, telemetry, weather, CO2, a world map of your network connections and a glowing 3D brain.
- **Talk to it.** Say "Hey Jarvis" (optional wake word) or press **F6**. It listens (Whisper), thinks (your local model in LM Studio) and answers out loud (Kokoro). Say "stop" while it talks and it shuts up.
- **Everything local.** The AI runs on your PC through [LM Studio](https://lmstudio.ai). No cloud AI, no account.
- **Model control inside the HUD:** switch the LM Studio model, set the context size, toggle reasoning.
- **Philips Hue lights (optional):** "turn off the kitchen lights". Every change is read back from the bridge, so Jarvis cannot just claim it worked.
- **Tado heating (optional):** "heating off in the living room".
- **News headlines:** "BBC news" or "Hacker News headlines" with clickable links.
- **Web search (optional):** needs your own [Serply](https://serply.io) key.
- **Document search (experimental, fussy):** ask questions about your own files and get sources with links. Needs the LM Studio plugin *Big RAG* and some patience.
- **Privacy first:** upstream analytics (PostHog) are **switched off**. All Jarvis ports listen on `127.0.0.1` only. Keys never go into files in this repo.
- **English only on purpose.** The voice does not pronounce other languages correctly, so speech is set to English.

## What you need

| | |
|---|---|
| OS | **Windows 11** and **Windows PowerShell 5** (the blue one that comes with Windows, not PowerShell 7) |
| GPU | NVIDIA recommended (gauges need `nvidia-smi`). Built on an RTX 5090. Without a GPU the HUD still runs, the GPU gauges just show zeros. |
| RAM | 64 GB on my PC. 16 GB works with a small model. |
| Screen | Designed for 5120x1440 ultrawide. Smaller screens get a compact layout (tested at 1366x768). |
| Browser | Firefox (what I use). Allow the microphone. |
| Programs | Git, uv, Node.js, Rust, Windows Terminal, LM Studio. The installer offers to install any that are missing. |

## Disk space: plan for about 25 GB free

- **3.2 GB** the project folder after install (measured on my PC)
- **about 16 GB** the default model `google/gemma-4-26b-a4b-qat` (small PC? take `google/gemma-4-e2b`, about 4.4 GB)
- **a few hundred MB** voice model and wake word files

## Install

1. Install Git if you do not have it: `winget install --id Git.Git -e`
2. Open a **normal** (not admin) PowerShell and run:

```powershell
git clone -b ironman https://github.com/ChrisMan4000/IronMan-JARVIS.git
cd IronMan-JARVIS
powershell -ExecutionPolicy Bypass -File .\install-jarvis.ps1
```

3. The installer asks before every optional part (Hue, Tado, wake word, web search key). If it installs programs, it tells you to open a new PowerShell and run it again. Finished parts are skipped.
4. Open LM Studio once, run `lms bootstrap`, and download a model (see above).
5. Double-click the **Jarvis** icon on your desktop. Allow the microphone in the browser.

Set your city in `frontend/public/hud.html` (search for `HOME_CFG`). Four values: name, latitude, longitude, time zone. The default is London.

## Uninstall ("Project Jarvis" gone)

```powershell
cd IronMan-JARVIS
powershell -ExecutionPolicy Bypass -File .\uninstall-jarvis.ps1
```

It shows what it will remove and its size, and you must type `UNINSTALL` to continue. It removes the project folder, your Jarvis settings, keys and logs in `%USERPROFILE%\.openjarvis`, the desktop icon and the Jarvis environment settings. It **never** touches Git, Node, uv, Rust, LM Studio or your downloaded models. If you also use plain OpenJarvis, note that it shares the `.openjarvis` settings folder.

## Where does the HUD get its data?

See the annotated screenshot at the top. Here is the same information as text:

| # | Panel | Source |
|---|---|---|
| 1 | Hardware | `tools/hwstats.py` (port 8765): `nvidia-smi`, Windows counters, LM Studio |
| 2 | Diagnostics | OpenJarvis server: `/v1/telemetry/stats` and `/energy` |
| 3 | Core status | state of the voice loop in `hud.html`; latency = ping of the Jarvis server |
| 4 | Audio | level of your microphone and of Jarvis's voice (browser audio) |
| 5 | Core diagnostics | CPU/GPU charts from the helper. "SYNAPSE" is simulated |
| 6 | Voice ring | click or F6. Wake word: `tools/npu/wake_service.py` (8766). Whisper and Kokoro run locally |
| 7 | Fan speeds | real fan speeds (RPM) from LibreHardwareMonitor via the helper; the GPU fan comes from `nvidia-smi` |
| 8 | Chat | OpenJarvis (8000) to LM Studio (1234). Sources = your documents, links = web search |
| 9 | Chrono | your PC clock; CO2 from NOAA Mauna Loa, fetched by the helper |
| 10 | Data stream | the same telemetry as panel 2 |
| 11 | Weather | Open-Meteo.com for the city you set (temperature, wind, rain and sun likelihood for today) |
| 12 | Neural core | glows with voice level and "thinking" |
| 13 | Network traffic | connections from the helper, places from an offline DB-IP database |

## What goes over the internet

Honest list: weather (Open-Meteo, your city's coordinates), CO2 (NOAA), the world-map shape (jsDelivr), one-time downloads (voice model from Hugging Face, wake word files from GitHub, location database from DB-IP), and only if you enable them: web search (Serply), the news feeds you ask for, and your Hue bridge and Tado account. No usage data is sent anywhere.

## Safety notes

- `code_interpreter`, `file_read` and `shell_exec` are **off** by default. Text from a web page, a news item or a document can try to trick a model into using them (prompt injection). Turn them on in `config.toml` only if you understand that.
- Never share `hue-key.txt`, `tado-token.json` or your Serply key. The installer keeps them out of this folder.

## What changed from OpenJarvis?

See [NOTICE](NOTICE) for the full list of modified and added files (Apache-2.0, section 4b). Base version: OpenJarvis commit `1a9c8cf`.

## Roadmap

- **Next version: a useful agents setup.** Not the "look, an agent!" kind. The useful kind.
- Maybe: upgrade to the newest OpenJarvis once I have time to retest everything.

## License and thanks

Apache License 2.0, same as OpenJarvis (see [LICENSE](LICENSE)). Huge thanks to the OpenJarvis team, LM Studio, Kokoro, Whisper, openWakeWord, Open-Meteo, NOAA and DB-IP. Built with a lot of help from Claude.

*Fan project, not affiliated with Marvel, Disney or the OpenJarvis authors. "Iron Man" and "J.A.R.V.I.S." are their owners' trademarks and are used here as a homage.*
