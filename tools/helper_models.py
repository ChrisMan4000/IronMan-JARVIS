"""Model control for the HUD: /m/list, /m/set, /m/load, plus the capability check.

Saved per model in ~/.openjarvis: hud-model-settings.json (reasoning, thinking,
context) and hud-model-caps.json (does the model react to the reasoning / thinking
switches). Model ids are checked against LM Studio's own list before any command runs.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

from helper_http import Handler, need_trusted, query, send
from helper_stats import (
    BYTES_PER_GB,
    JARVIS_DIR,
    LMSTUDIO_MODELS_URL,
    NO_WINDOW,
    program,
    stats,
)

logger = logging.getLogger(__name__)

SETTINGS_PATH = os.path.join(JARVIS_DIR, "hud-model-settings.json")
CAPS_PATH = os.path.join(JARVIS_DIR, "hud-model-caps.json")
SET_DEFAULTS = {"reasoning": False, "thinking": False, "context": 8192}
CONTEXT_RANGE = (1024, 1048576)
CHAT_URL = "http://localhost:1234/v1/chat/completions"
PROBE_QUESTION = "What is 17 times 23? Answer with the number only."
PROBE_RETRY_AFTER = 300  # seconds before a failed capability check is tried again

_set_lock = threading.Lock()
_caps_lock = threading.Lock()
_load_lock = threading.Lock()  # one "is it busy? then start" decision at a time
_load_state: dict[str, Any] = {"loading": None, "error": None}
_probing: dict[str, Any] = {"model": None}
_probe_failed: dict[str, float] = {}
_sizes: dict[str, Any] = {"t": 0.0, "m": {}}


# ----------------------------------------------------------------- saved json files
def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):  # first run, or a damaged file: start empty
        return {}


def _write_json_atomic(path: str, data: dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def read_settings() -> dict[str, Any]:
    return _read_json(SETTINGS_PATH)


def read_caps() -> dict[str, Any]:
    return _read_json(CAPS_PATH)


def get_setting(model: str) -> dict[str, Any]:
    d = dict(SET_DEFAULTS)
    d.update(read_settings().get(model, {}))
    return d


def put_setting(model: str, **kw: Any) -> dict[str, Any]:
    """Save per-model settings (reasoning, thinking, context) atomically."""
    with _set_lock:
        every_model = read_settings()
        cur = dict(SET_DEFAULTS)
        cur.update(every_model.get(model, {}))
        cur.update(kw)
        every_model[model] = cur
        _write_json_atomic(SETTINGS_PATH, every_model)
        return cur


def settings_from_query(q: dict[str, str]) -> dict[str, Any]:
    """The /m/set changes present in the query (context is clamped to CONTEXT_RANGE)."""
    kw: dict[str, Any] = {}
    for switch in ("reasoning", "thinking"):
        if switch in q:
            kw[switch] = q[switch] == "1"
    if "context" in q:
        kw["context"] = max(CONTEXT_RANGE[0], min(int(q["context"]), CONTEXT_RANGE[1]))
    return kw


# ------------------------------------------------------------------------ LM Studio
def _lms(*args: str, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        [program("lms"), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=NO_WINDOW,
    )


def model_sizes() -> dict[str, float]:
    """modelKey -> size in GB from 'lms ls --json' (refreshed every 2 minutes)."""
    if time.time() - _sizes["t"] > 120:
        _sizes["t"] = time.time()
        try:
            listed = json.loads(_lms("ls", "--json", timeout=15).stdout)
            _sizes["m"] = {
                m["modelKey"]: round(m["sizeBytes"] / BYTES_PER_GB, 1)
                for m in listed
                if m.get("modelKey") and m.get("sizeBytes")
            }
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            logger.debug("lms ls failed: %s", exc)
    return _sizes["m"]


def list_models() -> list[dict[str, Any]]:
    """All LLMs known to LM Studio with state, context, size and saved settings."""
    with urllib.request.urlopen(LMSTUDIO_MODELS_URL, timeout=5) as r:  # nosec B310 - fixed local URL
        data = json.load(r).get("data", [])
    caps, sizes = read_caps(), model_sizes()
    out = []
    for m in data:
        if m.get("type") not in ("llm", "vlm"):
            continue
        row = {
            "id": m["id"],
            "state": m.get("state"),
            "max": m.get("max_context_length"),
            "size_gb": sizes.get(m["id"]),
            "loaded_ctx": m.get("loaded_context_length"),
        }
        row.update(get_setting(m["id"]))
        c = caps.get(m["id"])
        row["caps"] = (
            {"reasoning": c["reasoning"], "thinking": c["thinking"]} if c else None
        )
        row["probing"] = _probing["model"] == m["id"]
        out.append(row)
    return out


def _do_load(mid: str, ctx: int) -> None:
    """Unload everything, then load one model with its saved context (in a thread)."""
    try:
        subprocess.run(
            [program("lms"), "unload", "--all"], timeout=60, capture_output=True
        )
        r = subprocess.run(
            [program("lms"), "load", mid, "-c", str(ctx), "-y"],
            timeout=300,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            _load_state["error"] = ((r.stderr or "") + (r.stdout or ""))[
                -200:
            ] or "load failed"
    except (OSError, subprocess.SubprocessError) as e:
        _load_state["error"] = str(e)[:200]
    finally:
        _load_state["loading"] = None


def start_load(mid: str) -> dict[str, Any]:
    """Start loading a model unless a load is already running."""
    with _load_lock:
        if _load_state["loading"]:
            return {"error": "busy"}
        ctx = get_setting(mid)["context"]
        _load_state.update(
            loading=mid, error=None
        )  # set before the thread starts: no double load
    threading.Thread(target=_do_load, args=(mid, ctx), daemon=True).start()
    return {"loading": mid, "context": ctx}


def serve_model_api(h: Handler) -> None:
    """/m/list (read); /m/set and /m/load only from the HUD, only for known models."""
    op = urllib.parse.urlparse(h.path).path[len("/m/") :]
    q = query(h)
    if op in ("set", "load") and not need_trusted(h):
        return
    try:
        if op == "list":
            res = {
                "models": list_models(),
                "loading": _load_state["loading"],
                "error": _load_state["error"],
            }
        elif op in ("set", "load"):
            mid = q.get("model", "")
            if mid not in {m["id"] for m in list_models()}:
                res = {"error": "unknown model"}
            elif op == "set":
                res = put_setting(mid, **settings_from_query(q))
            else:
                res = start_load(mid)
        else:
            res = {"error": "unknown"}
    except Exception as e:
        # LM Studio down or a bad number: the HUD shows the short text.
        res = {"error": str(e)[:200]}
    send(h, 200, res)


# ----------------------------------------------------------------- capability check
def _probe_call(model: str, extra: dict[str, Any]) -> tuple[int, bool]:
    """One tiny test question to LM Studio: (answer tokens, had reasoning text)."""
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": PROBE_QUESTION}],
        **extra,
    }
    req = urllib.request.Request(
        CHAT_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:  # nosec B310 - fixed local URL
        j = json.load(r)
    msg = j["choices"][0]["message"]
    tokens = int((j.get("usage") or {}).get("completion_tokens", 0))
    reasoning = bool(
        (msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
    )
    return tokens, reasoning or "<think>" in (msg.get("content") or "")


def switch_matters(off: tuple[int, bool], on: tuple[int, bool]) -> bool:
    """True when the switch changed whether reasoning shows, or the length by 1.5x."""
    return off[1] != on[1] or max(off[0], on[0]) >= 1.5 * max(1, min(off[0], on[0]))


def probe_model(model: str) -> None:
    """Test both switches (off and on) and save the result in hud-model-caps.json."""
    _probing["model"] = model
    try:
        r_off = _probe_call(model, {"reasoning_effort": "none"})
        r_on = _probe_call(model, {"reasoning_effort": "medium"})
        t_off = _probe_call(model, {"chat_template_kwargs": {"enable_thinking": False}})
        t_on = _probe_call(model, {"chat_template_kwargs": {"enable_thinking": True}})
        res = {
            "reasoning": switch_matters(r_off, r_on),
            "thinking": switch_matters(t_off, t_on),
            "detail": {
                "r_off": list(r_off),
                "r_on": list(r_on),
                "t_off": list(t_off),
                "t_on": list(t_on),
            },
        }
        with _caps_lock:
            every_model = read_caps()
            every_model[model] = res
            _write_json_atomic(CAPS_PATH, every_model)
    except (
        OSError,
        ValueError,
        KeyError,
        IndexError,
    ) as exc:  # model busy or unloaded mid-test
        logger.debug("capability check of %s failed: %s", model, exc)
    finally:
        _probing["model"] = None


def caps_step() -> None:
    """Test a newly loaded model once (retry a failed test after a few minutes)."""
    m = stats.get("model")
    if (
        not m
        or _probing["model"]
        or m in read_caps()
        or time.time() - _probe_failed.get(m, 0) <= PROBE_RETRY_AFTER
    ):
        return
    probe_model(m)
    if m not in read_caps():
        _probe_failed[m] = time.time()


def start() -> None:
    from helper_stats import every

    def delayed() -> None:
        time.sleep(5)  # let the model loop find the loaded model first
        every(5, caps_step)()

    threading.Thread(target=delayed, daemon=True).start()
