"""Oxxify ventilation tool: Oxxify smart 50 units (Blauberg Vento protocol).

Local only: UDP port 4000 inside your Wi-Fi, no cloud, no account.
Settings (unit address, id, password) live in ~/.openjarvis/oxxify.json, written by
`uv run --no-sync python tools\\oxxify.py setup`. The password never goes into this
repo or into a log.

Actions: status, on, off, speed (1-3), mode (ventilation / heat recovery / supply
air), night (8 h on speed 1), party (4 h on speed 3), timer_off, humidity (target
40-80 %, turns the humidity sensor on). Every change is read back from the unit;
success means the read-back confirmed it.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import device_log
from openjarvis.tools import oxxify_protocol as proto
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.oxxify_protocol import (
    DEFAULT_PASSWORD,
    F_WRITE,
    MODES,
    P_HUM_ON,
    P_HUM_SET,
    P_MODE,
    P_POWER,
    P_SPEED,
    P_TIMER,
    TIMERS,
    AuthError,
    VentStatus,
)

T = TypeVar("T")

TOOL_NAME = "oxxify_vent"
CFG_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "oxxify.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "oxxify-set-log.txt")
DEFAULT_NAME = "Ventilation"
VENT_READ_BACK_DELAY = 1.0  # seconds before the unit reports a change

# Words that pick a mode, in this order ("recovery ventilation" -> heat recovery).
MODE_WORDS = (
    (1, ("recover", "regen", "alternat")),
    (2, ("supply",)),
    (0, ("vent", "exhaust")),
)

# The HUD helper and the tool may rediscover at the same time.
_cfg_lock = threading.Lock()


# ---------------------------------------------------------------------------- settings
def load_cfg() -> dict[str, str]:
    """Saved settings with defaults filled in: ip, id, password, name."""
    with open(CFG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("password", DEFAULT_PASSWORD)
    cfg.setdefault("name", DEFAULT_NAME)
    return cfg


def save_cfg(cfg: dict[str, str]) -> None:
    """Write oxxify.json via a .tmp file, so a crash never leaves half a file."""
    os.makedirs(os.path.dirname(CFG_FILE), exist_ok=True)
    with open(CFG_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(CFG_FILE + ".tmp", CFG_FILE)


def call_with_rediscovery(cfg: dict[str, str], fn: Callable[[str], T]) -> T:
    """Run fn(ip); if the unit got a new address from the router, find it by its id.

    The new address is saved to oxxify.json. Raises OSError when the unit is not found.
    """
    try:
        return fn(cfg["ip"])
    except OSError:
        for ip, did in proto.discover(cfg["password"]):
            if did == cfg["id"] and ip != cfg["ip"]:
                with _cfg_lock:
                    cfg["ip"] = ip
                    save_cfg(cfg)
                return fn(ip)
        raise


def read_configured_status(cfg: dict[str, str]) -> VentStatus:
    """Status of the configured unit, finding it again if its address changed."""
    return call_with_rediscovery(
        cfg, lambda ip: proto.read_status(ip, cfg["id"], cfg["password"])
    )


def describe(st: VentStatus, name: str = DEFAULT_NAME) -> str:
    """One readable line about the unit."""
    if not st["power"]:
        return "%s: OFF" % name
    speed = "manual" if st["speed"] == 255 else str(st["speed"])
    text = "%s: ON, speed %s, mode %s" % (name, speed, st["mode"])
    if st["timer"] != "off":
        text += ", %s timer running" % st["timer"]
    if st["humidity"] is not None:
        text += ", room humidity %s%%" % st["humidity"]
    if st["humidity_sensor_on"] and st["humidity_target"]:
        text += " (target %s%%)" % st["humidity_target"]
    if st["fan_rpm"]:
        text += ", fan %s rpm" % st["fan_rpm"]
    if st["filter_due"]:
        text += ", FILTER NEEDS CHANGING"
    elif st["filter_days_left"] is not None:
        text += ", filter due in %s days" % st["filter_days_left"]
    if st["alarm"] != "none":
        text += ", %s reported" % st["alarm"].upper()
    return text


# ---------------------------------------------------------------------------- planning
Plan = tuple[dict[int, int], Callable[[VentStatus], bool]]  # (writes, read-back check)


def _digits(value: str) -> int | None:
    found = "".join(c for c in value if c.isdigit())
    return int(found) if found else None


def mode_from_words(value: str) -> int | None:
    for mode, words in MODE_WORDS:
        if any(w in value for w in words):
            return mode
    return None


TIMER_ACTIONS = {"night": 1, "party": 2, "timer_off": 0}
HUMIDITY_RANGE = (40, 80)  # percent; the unit offers steps of 10


def _plan_speed(value: str) -> Plan | str:
    n = _digits(value)
    if n not in (1, 2, 3):
        return "Speed must be 1, 2 or 3."
    return {P_POWER: 1, P_SPEED: n}, lambda s: s["power"] and s["speed"] == n


def _plan_mode(value: str) -> Plan | str:
    m = mode_from_words(value)
    if m is None:
        return "Mode must be ventilation, heat recovery or supply air."
    return {P_POWER: 1, P_MODE: m}, lambda s: s["mode"] == MODES[m]


def _plan_humidity(value: str) -> Plan | str:
    h = _digits(value) or 0
    if not HUMIDITY_RANGE[0] <= h <= HUMIDITY_RANGE[1]:
        return "Humidity target must be between 40 and 80 percent."
    h = int(round(h / 10.0) * 10)
    return {P_HUM_ON: 1, P_HUM_SET: h}, (
        lambda s: s["humidity_sensor_on"] and s["humidity_target"] == h
    )


def _plan_timer(timer: int) -> Plan:
    writes = {P_TIMER: timer} if timer == 0 else {P_POWER: 1, P_TIMER: timer}
    return writes, lambda s: s["timer"] == TIMERS[timer]


PLANNERS: dict[str, Callable[[str], Plan | str]] = {
    "on": lambda _v: ({P_POWER: 1}, lambda s: s["power"]),
    "off": lambda _v: ({P_POWER: 0}, lambda s: not s["power"]),
    "speed": _plan_speed,
    "mode": _plan_mode,
    "humidity": _plan_humidity,
    **{name: (lambda _v, t=t: _plan_timer(t)) for name, t in TIMER_ACTIONS.items()},
}


def plan_change(action: str, value: str) -> Plan | str:
    """What to write for an action and how to check it afterwards, or an error text."""
    planner = PLANNERS.get(action)
    if planner is None:
        return (
            "Unknown action. Use status, on, off, speed, mode, night, party, timer_off"
            " or humidity."
        )
    return planner(value)


def _result(text: str, ok: bool = True) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=text, success=ok)


# ---------------------------------------------------------------------------- the tool
@ToolRegistry.register(TOOL_NAME)
class OxxifyVentTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
            description=(
                "ALWAYS call this tool when the user asks about or wants to change the"
                " ventilation, the ventilator, the fan for fresh air, air exchange, or"
                " the Oxxify. Never say the ventilation was changed unless this tool"
                " returned a result. Actions: status (power, speed, mode, room"
                " humidity, filter), on, off, speed (value 1, 2 or 3), mode (value:"
                " ventilation, heat recovery or supply air), night (8 hours on speed"
                " 1), party (4 hours on speed 3), timer_off (ends night or party),"
                " humidity (value 40 to 80: target room humidity, turns the humidity"
                " sensor on)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "status",
                            "on",
                            "off",
                            "speed",
                            "mode",
                            "night",
                            "party",
                            "timer_off",
                            "humidity",
                        ],
                    },
                    "value": {"type": "string"},
                },
                "required": ["action"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        action = str(params.get("action", "")).lower().strip().replace(" ", "_")
        value = str(params.get("value", "") or "").lower().strip()
        try:
            cfg = load_cfg()
        except (OSError, ValueError):  # missing or unreadable oxxify.json
            return _result(
                "Ventilation is not set up yet. Run: uv run --no-sync python"
                " tools\\oxxify.py setup",
                False,
            )
        try:
            if action == "status":
                return _result(describe(read_configured_status(cfg), cfg["name"]))
            plan = plan_change(action, value)
            if isinstance(plan, str):
                return _result(plan, False)
            writes, verify = plan
            # Writes get no answer that proves delivery, so make sure the address is
            # current first (this finds the unit again if the router moved it).
            read_configured_status(cfg)
            data = b"".join(bytes([k, v]) for k, v in writes.items())
            proto.udp_request(cfg["ip"], cfg["id"], cfg["password"], F_WRITE, data)
            device_log.append_change(LOG_FILE, "%s %s" % (action, value))
            time.sleep(VENT_READ_BACK_DELAY)
            st = read_configured_status(cfg)
            ok = verify(st)
            return _result(
                "Sent: %s %s. Read back from the unit: %s. Verified: %s"
                % (action, value, describe(st, cfg["name"]), "YES" if ok else "NO"),
                ok,
            )
        except AuthError:
            return _result(
                "The ventilation unit refused the password. Run tools\\oxxify.py setup"
                " again.",
                False,
            )
        except OSError:
            return _result(
                "The ventilation unit did not answer (is it powered and on the"
                " Wi-Fi?).",
                False,
            )
        except Exception as e:  # anything else becomes a short tool reply
            return _result("Ventilation error: %s" % type(e).__name__, False)
