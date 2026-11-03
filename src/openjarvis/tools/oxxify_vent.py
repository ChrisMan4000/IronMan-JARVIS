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
import socket
import threading
import time
from collections.abc import Callable
from typing import Any, TypedDict, TypeVar

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import device_log
from openjarvis.tools._stubs import BaseTool, ToolSpec

T = TypeVar("T")

TOOL_NAME = "oxxify_vent"
CFG_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "oxxify.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "oxxify-set-log.txt")
PORT = 4000
DEFAULT_ID = "DEFAULT_DEVICEID"
DEFAULT_PASSWORD = "1111"  # factory default of the Oxxify / impruf app
DEFAULT_NAME = "Ventilation"
READ_BACK_DELAY = 1.0  # seconds before the unit reports a change

# Vento function codes (first byte after the password) and parameter numbers.
F_READ, F_WRITE, F_RESPONSE, F_AUTH_FAIL = 0x01, 0x02, 0x06, 0x07
P_POWER, P_SPEED, P_BOOST, P_TIMER = 0x01, 0x02, 0x06, 0x07
P_HUM_ON, P_HUM_SET, P_HUM = 0x0F, 0x19, 0x25
P_MANUAL, P_FAN1, P_FAN2 = 0x44, 0x4A, 0x4B
P_FILTER_LEFT, P_DEVID, P_ALARM, P_FILTER_DUE, P_MODE = 0x64, 0x7C, 0x83, 0x88, 0xB7
STATUS_PARAMS = bytes(
    [
        P_POWER,
        P_SPEED,
        P_BOOST,
        P_TIMER,
        P_HUM_ON,
        P_HUM_SET,
        P_HUM,
        P_MANUAL,
        P_FAN1,
        P_FAN2,
        P_FILTER_LEFT,
        P_ALARM,
        P_FILTER_DUE,
        P_MODE,
    ]
)

MODES = {0: "ventilation", 1: "heat recovery", 2: "supply air"}
TIMERS = {0: "off", 1: "night", 2: "party"}
ALARMS = {0: "none", 1: "alarm", 2: "warning"}
# Words that pick a mode, in this order ("recovery ventilation" -> heat recovery).
MODE_WORDS = (
    (1, ("recover", "regen", "alternat")),
    (2, ("supply",)),
    (0, ("vent", "exhaust")),
)

_cfg_lock = (
    threading.Lock()
)  # the HUD helper and the tool may rediscover at the same time

Answer = tuple[str, str, dict[int, bytes]]  # (ip, device id, {param: value bytes})


class AuthError(Exception):
    """The unit answered, but refused the password."""


class VentStatus(TypedDict):
    power: bool
    speed: int  # 1-3, 255 = manual
    mode: str
    timer: str
    boost: bool
    humidity: int | None
    humidity_sensor_on: bool
    humidity_target: int | None
    fan_rpm: int
    filter_days_left: int | None
    filter_due: bool
    alarm: str


# ---------------------------------------------------------------------------- protocol
def build_packet(dev_id: str, pwd: str, func: int, data: bytes) -> bytes:
    """One Vento request: header, device id, password, function, data, checksum."""
    body = (
        bytes([0x02, len(dev_id)])
        + dev_id.encode()
        + bytes([len(pwd)])
        + pwd.encode()
        + bytes([func])
        + data
    )
    checksum = sum(body) & 0xFFFF
    return b"\xfd\xfd" + body + bytes([checksum & 0xFF, checksum >> 8])


def _decode_params(data: bytes) -> dict[int, bytes]:
    """Parameter block -> {param: value bytes} (0xFF page, 0xFE size, 0xFD skip)."""
    out: dict[int, bytes] = {}
    i, page, size = 0, 0, 1
    while i < len(data):
        b = data[i]
        if b == 0xFF:  # next parameters are on another page
            page = data[i + 1] << 8
            i += 2
        elif b == 0xFE:  # next value is longer than one byte
            size = data[i + 1]
            i += 2
        elif b == 0xFD:  # the unit does not know this parameter
            i += 2
        else:
            out[page | b] = data[i + 1 : i + 1 + size]
            i += 1 + size
            size = 1
    return out


def parse_packet(raw: bytes) -> tuple[str, int, dict[int, bytes]] | None:
    """(device id, function, {param: bytes}), or None for a broken or foreign answer."""
    if len(raw) < 8 or raw[0] != 0xFD or raw[1] != 0xFD:
        return None
    if (sum(raw[2:-2]) & 0xFFFF) != raw[-2] | (raw[-1] << 8):
        return None
    i = 3
    n = raw[i]
    dev_id = raw[i + 1 : i + 1 + n].decode(errors="replace")
    i += 1 + n
    i += 1 + raw[i]  # skip the password echo
    func = raw[i]
    return dev_id, func, _decode_params(raw[i + 1 : -2])


def probe(
    ip: str, dev_id: str, pwd: str, func: int, data: bytes, timeout: float = 2.0
) -> bytes | None:
    """Send one request and return the raw answer, or None if the unit stays silent."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(build_packet(dev_id, pwd, func, data), (ip, PORT))
        try:
            return s.recvfrom(1024)[0]
        except socket.timeout:
            return None


def _udp_request(
    ip: str,
    dev_id: str,
    pwd: str,
    func: int,
    data: bytes,
    timeout: float = 2.0,
    broadcast: bool = False,
) -> list[Answer]:
    """Send a request; return the readable answers (one unit, or all on broadcast).

    Raises AuthError when a single unit refuses the password. Silence is an empty list.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        if broadcast:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        s.sendto(build_packet(dev_id, pwd, func, data), (ip, PORT))
        answers: list[Answer] = []
        while True:
            try:
                raw, addr = s.recvfrom(1024)
            except socket.timeout:
                break
            reply = parse_packet(raw)
            if reply:
                if reply[1] == F_AUTH_FAIL and not broadcast:
                    raise AuthError("wrong password")
                if reply[1] == F_RESPONSE:
                    answers.append((addr[0], reply[0], reply[2]))
            if not broadcast:
                break
        return answers


def discover(
    pwd: str = DEFAULT_PASSWORD, timeout: float = 3.0
) -> list[tuple[str, str]]:
    """Units on the home network: [(ip, device_id)]."""
    found = {}
    ask = bytes([P_DEVID])
    for ip, _, prm in _udp_request(
        "255.255.255.255", DEFAULT_ID, pwd, F_READ, ask, timeout, broadcast=True
    ):
        did = prm.get(P_DEVID, b"").decode(errors="replace").strip("\x00")
        if did:
            found[ip] = did
    return sorted(found.items())


def _le_int(b: bytes | None) -> int:
    return int.from_bytes(b, "little") if b else 0


def _read_params(ip: str, dev_id: str, pwd: str) -> dict[int, bytes]:
    answers = _udp_request(ip, dev_id, pwd, F_READ, STATUS_PARAMS, timeout=1.0)
    if answers:
        return answers[0][2]
    # Some units stay silent when one asked number is unknown to them: ask one by one.
    params: dict[int, bytes] = {}
    for k in STATUS_PARAMS:
        single = _udp_request(ip, dev_id, pwd, F_READ, bytes([k]), timeout=0.6)
        if single:
            params.update(single[0][2])
    if P_POWER not in params:
        raise OSError("no answer")
    return params


def read_status(ip: str, dev_id: str, pwd: str) -> VentStatus:
    """What the unit is doing now. Raises OSError when it does not answer."""
    p = _read_params(ip, dev_id, pwd)
    filter_left = p.get(P_FILTER_LEFT, b"")
    return {
        "power": _le_int(p.get(P_POWER)) == 1,
        "speed": _le_int(p.get(P_SPEED)),
        "mode": MODES.get(_le_int(p.get(P_MODE)), "unknown"),
        "timer": TIMERS.get(_le_int(p.get(P_TIMER)), "unknown"),
        "boost": _le_int(p.get(P_BOOST)) == 1,
        "humidity": _le_int(p.get(P_HUM)) if P_HUM in p else None,
        "humidity_sensor_on": _le_int(p.get(P_HUM_ON)) == 1,
        "humidity_target": _le_int(p.get(P_HUM_SET)) if P_HUM_SET in p else None,
        "fan_rpm": max(_le_int(p.get(P_FAN1)), _le_int(p.get(P_FAN2))),
        "filter_days_left": filter_left[2] if len(filter_left) >= 3 else None,
        "filter_due": _le_int(p.get(P_FILTER_DUE)) == 1,
        "alarm": ALARMS.get(_le_int(p.get(P_ALARM)), "unknown"),
    }


# ---------------------------------------------------------------------------- settings
def load_cfg() -> dict[str, str]:
    """Saved settings with defaults filled in: ip, id, password, name."""
    with open(CFG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("password", DEFAULT_PASSWORD)
    cfg.setdefault("name", DEFAULT_NAME)
    return cfg


def save_cfg(cfg: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(CFG_FILE), exist_ok=True)
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def call_with_rediscovery(cfg: dict[str, str], fn: Callable[[str], T]) -> T:
    """Run fn(ip); if the unit got a new address from the router, find it by its id.

    The new address is saved to oxxify.json. Raises OSError when the unit is not found.
    """
    try:
        return fn(cfg["ip"])
    except OSError:
        for ip, did in discover(cfg["password"]):
            if did == cfg["id"] and ip != cfg["ip"]:
                with _cfg_lock:
                    cfg["ip"] = ip
                    save_cfg(cfg)
                return fn(ip)
        raise


def read_configured_status(cfg: dict[str, str]) -> VentStatus:
    """Status of the configured unit, finding it again if its address changed."""
    return call_with_rediscovery(
        cfg, lambda ip: read_status(ip, cfg["id"], cfg["password"])
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


def _log_change(text: str) -> None:
    device_log.append_change(LOG_FILE, text)


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
            _udp_request(cfg["ip"], cfg["id"], cfg["password"], F_WRITE, data)
            _log_change("%s %s" % (action, value))
            time.sleep(READ_BACK_DELAY)
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
