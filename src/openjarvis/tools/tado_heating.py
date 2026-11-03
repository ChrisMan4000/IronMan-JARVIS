"""Tado heating tool: read and control the Tado radiator valves through Tado's cloud.

Actions: status, set, boost, off, resume. Every change is read back; success means
the read-back confirmed it (Tado's cloud can lag, so it is checked a few times).

Security rules:
- Temperatures are checked with a strict range test that also rejects NaN / infinity.
- The login token file is only read here, never printed or logged.
- Changes are logged to tado-set-log.txt (action, zone, result - no secrets).
"""

from __future__ import annotations

import logging
import math
import os
import re
import sys
import time
from datetime import timedelta
from typing import Any

try:  # installed by the installer; without it the tool answers "not set up"
    from PyTado.interface.interface import Tado
    from PyTado.types import OverlayMode, Power
except ImportError:
    Tado = OverlayMode = Power = None

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import device_log
from openjarvis.tools._stubs import BaseTool, ToolSpec

TOOL_NAME = "tado_heating"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "tado-token.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "tado-set-log.txt")
MIN_TEMP = 5.0  # lowest allowed target (deg C)
MAX_TEMP = 25.0  # highest allowed target (deg C)
BOOST_TEMP = 25.0
BOOST_MIN = 30
BOOST_RANGE = (5, 120)  # allowed boost minutes
READ_BACK_TRIES = 3  # Tado's cloud often needs a few seconds to show a change
TADO_READ_BACK_DELAY = 2.0  # seconds between read-back tries
ZONE_FILLER = re.compile(r"\b(the|heating|radiators?|thermostats?|valves?)\b")
CHANGE_ACTIONS = ("set", "boost", "off", "resume")


def _valid_temp(t: object) -> bool:
    """True only for a real number from MIN_TEMP to MAX_TEMP (NaN, infinity refused)."""
    return (
        isinstance(t, (int, float)) and math.isfinite(t) and MIN_TEMP <= t <= MAX_TEMP
    )


def _quiet_pytado_loggers() -> None:
    """Silence PyTado's debug output.

    PyTado builds its own Logger objects with their own handler and level, outside the
    logging.getLogger() tree, so a parent logger level does not reach them: they have
    to be found in PyTado's modules.
    """
    for mod_name, mod in list(sys.modules.items()):
        if mod_name.startswith("PyTado") and mod is not None:
            for obj in list(vars(mod).values()):
                if isinstance(obj, logging.Logger):
                    obj.setLevel(logging.WARNING)


def open_tado_api() -> Any:
    """Tado client logged in with the saved token (tools\\tado_login.py creates it).

    Raises FileNotFoundError when there is no token yet; PyTado errors pass through.
    """
    if Tado is None:
        raise RuntimeError("PyTado is not installed (install-jarvis.ps1 adds it)")
    _quiet_pytado_loggers()  # PyTado's loggers exist once its modules are imported
    return Tado(token_file_path=TOKEN_FILE)  # passes calls on to the logged-in API


def zone_id(zone: Any) -> int:
    """PyTado keeps the zone id only in a private attribute; read it in one place."""
    return zone._id


def find_zone(zones: list[Any], text: object) -> tuple[Any | None, str]:
    """Zone by spoken name (exact, else unique partial): (zone, "") or (None, why)."""
    wanted = " ".join(ZONE_FILLER.sub(" ", str(text or "").lower().strip()).split())
    names = ", ".join(z.name for z in zones)
    exact = [z for z in zones if z.name.lower() == wanted]
    if len(exact) == 1:
        return exact[0], ""
    if len(exact) > 1:
        return None, "Several zones share that name. Zones: " + names
    partial = [z for z in zones if wanted and wanted in z.name.lower()]
    if len(partial) == 1:
        return partial[0], ""
    return None, "No such zone. Zones: " + names


def describe_zone(z: Any) -> str:
    """One readable line describing a zone."""
    power = getattr(z.power, "value", z.power)
    text = "%s: now %s C, target %s C, power %s, heating %s%%" % (
        z.name,
        z.current_temp,
        z.target_temp,
        power,
        z.heating_power_percentage,
    )
    text += ", manual override" if z.overlay_active else ", following schedule"
    if z.open_window:
        text += ", open window detected"
    if not z.available:
        text += " (NOT AVAILABLE)"
    return text


def _result(text: str, ok: bool = True) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=text, success=ok)


class InputError(ValueError):
    """The request cannot be sent as given; the message goes back to the user."""


def _temperature(raw: object, default: float | None = None) -> float:
    """A valid target temperature; InputError explains what is wrong."""
    try:
        temp = float(raw if raw not in (None, "") else default)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise InputError(
            "Temperature missing." if default is None else "Bad temperature or minutes."
        ) from None
    if not _valid_temp(temp):
        raise InputError(
            "Temperature must be between %s and %s C." % (MIN_TEMP, MAX_TEMP)
        )
    return temp


def matches(action: str, zone: Any, temp: float | None) -> bool:
    """Does a zone read back from Tado show the requested change?"""
    if action in ("set", "boost"):
        target = zone.target_temp
        return (
            bool(zone.overlay_active)
            and target is not None
            and abs(float(target) - temp) < 0.1
        )
    if action == "off":
        return str(getattr(zone.power, "value", zone.power)) == "OFF"
    return not zone.overlay_active  # resume: back on the schedule


@ToolRegistry.register(TOOL_NAME)
class TadoHeatingTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
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

    def _send(
        self, api: Any, action: str, zid: int, params: dict[str, Any]
    ) -> tuple[str, float | None]:
        """Check the inputs, send the change: (what was sent, target temp or None).

        Raises InputError before anything is sent when an input is wrong.
        """
        if action == "set":
            temp = _temperature(params.get("temperature"))
            api.set_zone_overlay(zid, OverlayMode.MANUAL, set_temp=temp)
            return "set to %s C until resumed" % temp, temp
        if action == "boost":
            temp = _temperature(params.get("temperature"), BOOST_TEMP)
            try:
                mins = int(params.get("minutes") or BOOST_MIN)
            except (TypeError, ValueError):
                raise InputError("Bad temperature or minutes.") from None
            if not BOOST_RANGE[0] <= mins <= BOOST_RANGE[1]:
                raise InputError("Minutes must be between %s and %s." % BOOST_RANGE)
            api.set_zone_overlay(
                zid, OverlayMode.TIMER, set_temp=temp, duration=timedelta(minutes=mins)
            )
            return "boost to %s C for %s min" % (temp, mins), temp
        if action == "off":
            api.set_zone_overlay(zid, OverlayMode.MANUAL, power=Power.OFF)
            return "heating off until resumed", None
        api.reset_zone_overlay(zid)
        return "back to schedule", None

    def execute(self, **params: Any) -> ToolResult:
        action = str(params.get("action", "")).lower().strip()
        try:
            api = open_tado_api()
            zones = api.get_zones()
            if action == "status":  # read-only
                return _result("\n".join(describe_zone(z) for z in zones))
            if action not in CHANGE_ACTIONS:
                return _result(
                    "Unknown action. Use status, set, boost, off or resume.", False
                )
            zone, why = find_zone(zones, params.get("room"))
            if zone is None:
                return _result(why, False)
            zid = zone_id(zone)
            sent, temp = self._send(api, action, zid, params)
            device_log.append_change(
                LOG_FILE, "%s | %s | %s" % (action, zone.name, sent)
            )
            for _ in range(READ_BACK_TRIES):
                time.sleep(TADO_READ_BACK_DELAY)
                now = next(z for z in api.get_zones() if zone_id(z) == zid)
                ok = matches(action, now, temp)
                if ok:
                    break
            text = "Sent: %s %s. Read back from Tado: %s. Verified: %s" % (
                zone.name,
                sent,
                describe_zone(now),
                "YES" if ok else "NO (Tado may need a few more seconds)",
            )
            return _result(text, ok)
        except InputError as e:
            return _result(str(e), False)
        except FileNotFoundError:
            return _result(
                "Tado is not logged in yet. Run: uv run --no-sync python"
                " tools\\tado_login.py",
                False,
            )
        except Exception as e:  # PyTado and network errors become a short tool reply
            return _result("Tado error: %s" % type(e).__name__, False)
