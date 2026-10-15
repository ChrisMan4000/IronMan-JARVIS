"""Tado heating tool: read and control the Tado radiator valves through Tado's cloud.

Actions: status, set, boost, off, resume. Every change is read back and verified.

Security notes (2026-10-14):
- Temperatures are checked with a strict range test that also rejects NaN / infinity.
- The login token file is only read here, never printed or logged.
- Changes are logged to tado-set-log.txt (action, zone, result - no secrets).
"""
from __future__ import annotations

import logging
import os
import math
import re
import time
from datetime import datetime, timedelta
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "tado-token.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "tado-set-log.txt")
MIN_TEMP = 5.0   # lowest allowed target (deg C)
MAX_TEMP = 25.0  # highest allowed target (deg C)
BOOST_TEMP = 25.0
BOOST_MIN = 30


# ---------------------------------------------------------------- helpers
def _valid_temp(t) -> bool:
    """True only for a real number between MIN_TEMP and MAX_TEMP (NaN and infinity are refused)."""
    return isinstance(t, (int, float)) and math.isfinite(t) and MIN_TEMP <= t <= MAX_TEMP


def _api():
    """Open the Tado API with the saved token and silence PyTado's debug logging."""
    from PyTado.interface.interface import Tado

    t = Tado(token_file_path=TOKEN_FILE)
    t._ensure_api_initialized()
    import sys

    for mod_name, mod in list(sys.modules.items()):
        if mod_name.startswith("PyTado") and mod is not None:
            for obj in list(vars(mod).values()):
                if isinstance(obj, logging.Logger):
                    obj.setLevel(logging.WARNING)
    return t._api


def _find(zones, text):
    """Find one zone by name (exact, else unique partial). Returns (zone, error_text)."""
    q = str(text or "").lower().strip()
    q = re.sub(r"\b(the|heating|radiators?|thermostats?|valves?)\b", " ", q)
    q = " ".join(q.split())
    names = ", ".join(z.name for z in zones)
    exact = [z for z in zones if z.name.lower() == q]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, "Several zones share that name. Zones: " + names
    part = [z for z in zones if q and q in z.name.lower()]
    if len(part) == 1:
        return part[0], None
    return None, "No such zone. Zones: " + names


def _desc(z):
    """One readable line describing a zone."""
    pw = getattr(z.power, "value", z.power)
    text = "%s: now %s C, target %s C, power %s, heating %s%%" % (
        z.name, z.current_temp, z.target_temp, pw, z.heating_power_percentage,
    )
    text += ", manual override" if z.overlay_active else ", following schedule"
    if z.open_window:
        text += ", open window detected"
    if not z.available:
        text += " (NOT AVAILABLE)"
    return text


# ---------------------------------------------------------------- the tool
@ToolRegistry.register("tado_heating")
class TadoHeatingTool(BaseTool):
    tool_id = "tado_heating"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="tado_heating",
            description=(
                "ALWAYS call this tool when the user asks about or wants to"
                " change the Tado radiators, heating or room temperature."
                " Never say the heating was changed unless this tool"
                " returned a result. Actions: status (all zones, no room"
                " needed), set (room + temperature 5 to 25 C, stays until"
                " resume), boost (room, heats to 25 C for 30 minutes, then"
                " returns to the schedule; optional temperature and"
                " minutes), off (room heating off), resume (room back to its"
                " schedule). Zones: Living Room, Temp Sensor, Kitchen,"
                " Bathroom. Pass only the zone name as room."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "set", "boost", "off", "resume"],
                    },
                    "room": {"type": "string"},
                    "temperature": {"type": "number"},
                    "minutes": {"type": "integer"},
                },
                "required": ["action"],
            },
            category="smart-home",
        )

    def _log(self, text):
        """Append one line to tado-set-log.txt (failures are ignored)."""
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text))
        except Exception:
            pass

    def _res(self, text, ok=True):
        return ToolResult(tool_name="tado_heating", content=text, success=ok)

    def execute(self, **params: Any) -> ToolResult:
        action = str(params.get("action", "")).lower().strip()
        try:
            api = _api()
            zones = api.get_zones()
            if action == "status":  # read-only
                return self._res("\n".join(_desc(z) for z in zones))
            if action not in ("set", "boost", "off", "resume"):
                return self._res("Unknown action. Use status, set, boost, off or resume.", False)
            z, err = _find(zones, params.get("room"))
            if z is None:
                return self._res(err, False)
            zid = z._id
            temp = None
            mins = None
            from PyTado.types import OverlayMode, Power

            # Send the change (inputs are checked first).
            if action == "set":
                try:
                    temp = float(params.get("temperature"))
                except Exception:
                    return self._res("Temperature missing.", False)
                if not _valid_temp(temp):
                    return self._res("Temperature must be between %s and %s C." % (MIN_TEMP, MAX_TEMP), False)
                api.set_zone_overlay(zid, OverlayMode.MANUAL, set_temp=temp)
                sent = "set to %s C until resumed" % temp
            elif action == "boost":
                try:
                    temp = float(params.get("temperature") or BOOST_TEMP)
                    mins = int(params.get("minutes") or BOOST_MIN)
                except Exception:
                    return self._res("Bad temperature or minutes.", False)
                if not _valid_temp(temp):
                    return self._res("Temperature must be between %s and %s C." % (MIN_TEMP, MAX_TEMP), False)
                if mins < 5 or mins > 120:
                    return self._res("Minutes must be between 5 and 120.", False)
                api.set_zone_overlay(zid, OverlayMode.TIMER, set_temp=temp, duration=timedelta(minutes=mins))
                sent = "boost to %s C for %s min" % (temp, mins)
            elif action == "off":
                api.set_zone_overlay(zid, OverlayMode.MANUAL, power=Power.OFF)
                sent = "heating off until resumed"
            else:
                api.reset_zone_overlay(zid)
                sent = "back to schedule"
            self._log("%s | %s | %s" % (action, z.name, sent))

            # Read the zone back from Tado and report whether it matches.
            time.sleep(2.0)
            z2 = [x for x in api.get_zones() if x._id == zid][0]
            pw = str(getattr(z2.power, "value", z2.power))
            if action in ("set", "boost"):
                ok = bool(z2.overlay_active) and z2.target_temp is not None and abs(float(z2.target_temp) - temp) < 0.1
            elif action == "off":
                ok = pw == "OFF"
            else:
                ok = not z2.overlay_active
            text = "Sent: %s %s. Read back from Tado: %s. Verified: %s" % (
                z.name, sent, _desc(z2), "YES" if ok else "NO (Tado may need a few more seconds)",
            )
            return self._res(text, True)
        except Exception as e:
            return self._res("Tado error: %s" % type(e).__name__, False)
