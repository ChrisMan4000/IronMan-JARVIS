"""Oxxify ventilation tool: controls Oxxify smart 50 units (Blauberg Vento protocol) on the HOME network.

Local only: UDP port 4000 inside your Wi-Fi, no cloud, no account.
Settings (unit address, id, password) live in ~/.openjarvis/oxxify.json, written by
`uv run --no-sync python tools\\oxxify.py setup`. The password never goes into this repo or into a log.

Actions: status, on, off, speed (1-3), mode (ventilation / heat recovery / supply air),
night (8 h on speed 1), party (4 h on speed 3), timer_off, humidity (target 40-80 %, turns the humidity sensor on).
Every change is read back from the unit and verified.
"""
from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

CFG_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "oxxify.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "oxxify-set-log.txt")
PORT = 4000
DEFAULT_ID = "DEFAULT_DEVICEID"

P_POWER, P_SPEED, P_BOOST, P_TIMER = 0x01, 0x02, 0x06, 0x07
P_HUM_ON, P_HUM_SET, P_HUM = 0x0F, 0x19, 0x25
P_MANUAL, P_FAN1, P_FAN2 = 0x44, 0x4A, 0x4B
P_FILTER_LEFT, P_DEVID, P_ALARM, P_FILTER_DUE, P_MODE = 0x64, 0x7C, 0x83, 0x88, 0xB7

MODES = {0: "ventilation", 1: "heat recovery", 2: "supply air"}
TIMERS = {0: "off", 1: "night", 2: "party"}


class AuthError(Exception):
    """The unit answered, but refused the password."""


# ---------------------------------------------------------------- protocol
def _packet(dev_id: str, pwd: str, func: int, data: bytes) -> bytes:
    body = bytes([0x02, len(dev_id)]) + dev_id.encode() + bytes([len(pwd)]) + pwd.encode() + bytes([func]) + data
    cs = sum(body) & 0xFFFF
    return b"\xFD\xFD" + body + bytes([cs & 0xFF, cs >> 8])


def _params(data: bytes) -> dict:
    out, i, page, size = {}, 0, 0, 1
    while i < len(data):
        b = data[i]
        if b == 0xFF:
            page = data[i + 1] << 8; i += 2; continue
        if b == 0xFE:
            size = data[i + 1]; i += 2; continue
        if b == 0xFD:
            i += 2; continue
        out[page | b] = data[i + 1:i + 1 + size]
        i += 1 + size; size = 1
    return out


def _parse(raw: bytes):
    """(device id, func, {param: bytes}) or None for a broken answer."""
    if len(raw) < 8 or raw[0] != 0xFD or raw[1] != 0xFD:
        return None
    if (sum(raw[2:-2]) & 0xFFFF) != raw[-2] | (raw[-1] << 8):
        return None
    i = 3
    n = raw[i]; dev_id = raw[i + 1:i + 1 + n].decode(errors="replace"); i += 1 + n
    n = raw[i]; i += 1 + n
    func = raw[i]; i += 1
    return dev_id, func, _params(raw[i:-2])


def _req(ip, dev_id, pwd, func, data, timeout=2.0, broadcast=False):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if broadcast:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        s.sendto(_packet(dev_id, pwd, func, data), (ip, PORT))
        answers = []
        while True:
            try:
                raw, addr = s.recvfrom(1024)
            except socket.timeout:
                break
            r = _parse(raw)
            if r:
                if r[1] == 0x07 and not broadcast:
                    raise AuthError("wrong password")
                if r[1] == 0x06:
                    answers.append((addr[0], r[0], r[2]))
            if not broadcast:
                break
        return answers
    finally:
        s.close()


def discover(pwd: str = "1111", timeout: float = 3.0):
    """Units on the home network: [(ip, device_id)]."""
    found = {}
    for ip, _, prm in _req("255.255.255.255", DEFAULT_ID, pwd, 0x01, bytes([P_DEVID]), timeout, broadcast=True):
        did = prm.get(P_DEVID, b"").decode(errors="replace").strip("\x00")
        if did:
            found[ip] = did
    return sorted(found.items())


def _int(b) -> int:
    return int.from_bytes(b, "little") if b else 0


def read_status(ip: str, dev_id: str, pwd: str) -> dict:
    ask = bytes([P_POWER, P_SPEED, P_BOOST, P_TIMER, P_HUM_ON, P_HUM_SET, P_HUM, P_MANUAL, P_FAN1, P_FAN2,
                 P_FILTER_LEFT, P_ALARM, P_FILTER_DUE, P_MODE])
    a = _req(ip, dev_id, pwd, 0x01, ask, timeout=1.0)
    if a:
        p = a[0][2]
    else:
        # some units stay silent when one asked number is unknown to them: ask one by one
        p = {}
        for k in ask:
            r = _req(ip, dev_id, pwd, 0x01, bytes([k]), timeout=0.6)
            if r:
                p.update(r[0][2])
        if P_POWER not in p:
            raise OSError("no answer")
    fl = p.get(P_FILTER_LEFT, b"")
    return {
        "power": _int(p.get(P_POWER)) == 1,
        "speed": _int(p.get(P_SPEED)),
        "mode": MODES.get(_int(p.get(P_MODE)), "unknown"),
        "timer": TIMERS.get(_int(p.get(P_TIMER)), "unknown"),
        "boost": _int(p.get(P_BOOST)) == 1,
        "humidity": _int(p.get(P_HUM)) if P_HUM in p else None,
        "humidity_sensor_on": _int(p.get(P_HUM_ON)) == 1,
        "humidity_target": _int(p.get(P_HUM_SET)) if P_HUM_SET in p else None,
        "fan_rpm": max(_int(p.get(P_FAN1)), _int(p.get(P_FAN2))),
        "filter_days_left": fl[2] if len(fl) >= 3 else None,
        "filter_due": _int(p.get(P_FILTER_DUE)) == 1,
        "alarm": {0: "none", 1: "alarm", 2: "warning"}.get(_int(p.get(P_ALARM)), "unknown"),
    }


def load_cfg() -> dict:
    with open(CFG_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_cfg(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CFG_FILE), exist_ok=True)
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _call(cfg: dict, fn):
    """Runs fn(ip); if the unit got a new address from the router, finds it again by its id."""
    try:
        return fn(cfg["ip"])
    except OSError:
        for ip, did in discover(cfg.get("password", "1111")):
            if did == cfg["id"] and ip != cfg["ip"]:
                cfg["ip"] = ip
                save_cfg(cfg)
                return fn(ip)
        raise


def describe(st: dict, name: str = "Ventilation") -> str:
    if not st["power"]:
        return "%s: OFF" % name
    sp = "manual" if st["speed"] == 255 else str(st["speed"])
    t = "%s: ON, speed %s, mode %s" % (name, sp, st["mode"])
    if st["timer"] != "off":
        t += ", %s timer running" % st["timer"]
    if st["humidity"] is not None:
        t += ", room humidity %s%%" % st["humidity"]
    if st["humidity_sensor_on"] and st["humidity_target"]:
        t += " (target %s%%)" % st["humidity_target"]
    if st["fan_rpm"]:
        t += ", fan %s rpm" % st["fan_rpm"]
    if st["filter_due"]:
        t += ", FILTER NEEDS CHANGING"
    elif st["filter_days_left"] is not None:
        t += ", filter due in %s days" % st["filter_days_left"]
    if st["alarm"] != "none":
        t += ", %s reported" % st["alarm"].upper()
    return t


# ---------------------------------------------------------------- the tool
@ToolRegistry.register("oxxify_vent")
class OxxifyVentTool(BaseTool):
    tool_id = "oxxify_vent"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="oxxify_vent",
            description=(
                "ALWAYS call this tool when the user asks about or wants to change the"
                " ventilation, the ventilator, the fan for fresh air, air exchange, or the"
                " Oxxify. Never say the ventilation was changed unless this tool returned a"
                " result. Actions: status (power, speed, mode, room humidity, filter),"
                " on, off, speed (value 1, 2 or 3), mode (value: ventilation, heat recovery"
                " or supply air), night (8 hours on speed 1), party (4 hours on speed 3),"
                " timer_off (ends night or party), humidity (value 40 to 80: target room"
                " humidity, turns the humidity sensor on)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "on", "off", "speed", "mode", "night", "party", "timer_off", "humidity"],
                    },
                    "value": {"type": "string"},
                },
                "required": ["action"],
            },
            category="smart-home",
        )

    def _res(self, text, ok=True):
        return ToolResult(tool_name="oxxify_vent", content=text, success=ok)

    def _log(self, text):
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text))
        except Exception:
            pass

    def execute(self, **params: Any) -> ToolResult:
        action = str(params.get("action", "")).lower().strip().replace(" ", "_")
        val = str(params.get("value", "") or "").lower().strip()
        try:
            cfg = load_cfg()
        except Exception:
            return self._res("Ventilation is not set up yet. Run: uv run --no-sync python tools\\oxxify.py setup", False)
        did, pwd, name = cfg["id"], cfg.get("password", "1111"), cfg.get("name", "Ventilation")
        try:
            if action == "status":
                return self._res(describe(_call(cfg, lambda ip: read_status(ip, did, pwd)), name))

            # what to write, and how to check it afterwards
            if action == "on":
                w, chk = {P_POWER: 1}, lambda s: s["power"]
            elif action == "off":
                w, chk = {P_POWER: 0}, lambda s: not s["power"]
            elif action == "speed":
                digits = "".join(c for c in val if c.isdigit())
                if digits not in ("1", "2", "3"):
                    return self._res("Speed must be 1, 2 or 3.", False)
                n = int(digits)
                w, chk = {P_POWER: 1, P_SPEED: n}, lambda s: s["power"] and s["speed"] == n
            elif action == "mode":
                m = 1 if ("recover" in val or "regen" in val or "alternat" in val) else 2 if "supply" in val else 0 if ("vent" in val or "exhaust" in val) else None
                if m is None:
                    return self._res("Mode must be ventilation, heat recovery or supply air.", False)
                w, chk = {P_POWER: 1, P_MODE: m}, lambda s: s["mode"] == MODES[m]
            elif action in ("night", "party", "timer_off"):
                t = {"night": 1, "party": 2, "timer_off": 0}[action]
                w = {P_TIMER: t} if t == 0 else {P_POWER: 1, P_TIMER: t}
                chk = lambda s: s["timer"] == TIMERS[t]
            elif action == "humidity":
                digits = "".join(c for c in val if c.isdigit())
                h = int(digits) if digits else 0
                if not 40 <= h <= 80:
                    return self._res("Humidity target must be between 40 and 80 percent.", False)
                h = int(round(h / 10.0) * 10)  # the unit offers 40, 50, 60, 70, 80
                w, chk = {P_HUM_ON: 1, P_HUM_SET: h}, lambda s: s["humidity_sensor_on"] and s["humidity_target"] == h
            else:
                return self._res("Unknown action. Use status, on, off, speed, mode, night, party, timer_off or humidity.", False)

            data = b"".join(bytes([k, v]) for k, v in w.items())
            _call(cfg, lambda ip: _req(ip, did, pwd, 0x02, data))
            self._log("%s %s" % (action, val))
            time.sleep(1.0)
            st = _call(cfg, lambda ip: read_status(ip, did, pwd))
            return self._res("Sent: %s %s. Read back from the unit: %s. Verified: %s" % (
                action, val, describe(st, name), "YES" if chk(st) else "NO"))
        except AuthError:
            return self._res("The ventilation unit refused the password. Run tools\\oxxify.py setup again.", False)
        except OSError:
            return self._res("The ventilation unit did not answer (is it powered and on the Wi-Fi?).", False)
        except Exception as e:
            return self._res("Ventilation error: %s" % type(e).__name__, False)
