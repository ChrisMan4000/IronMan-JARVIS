"""Hue tool: control ONE Philips Hue lamp (not a whole room).

What it can do per lamp: on/off, brightness 1-100 %, a colour (name or #hex, only on
colour lamps) and a white temperature in kelvin (only on lamps with white tones).
It reads the lamp back after 0.6 s and reports "Verified: YES/NO".
Lamp names are the ones from the Hue app (hue_light_list shows them).
The lamp helpers here (lamp_info, set_lamp + LampChange, find_lamp) are also used
by the local home-world helper.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, TypedDict

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import hue_bridge
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.hue_colors import (
    COLORS,
    hex_to_xy,
    kelvin_to_mired,
    white_hex,
    xy_to_hex,
)

TOOL_NAME = "hue_light"
LAMP_FILLER = ("the", "light", "lights", "lamp", "lamps", "hue", "my", "in", "on", "at")
READ_BACK_DELAY = 0.6  # seconds before a single lamp reports its new state
BRI_MAX = 254  # the bridge's brightness scale is 1-254
PERCENT_TO_BRI = BRI_MAX / 100


class LampCapabilities(TypedDict):
    dim: bool
    color: bool
    ct: bool


class LampInfo(LampCapabilities):
    """Short form of one lamp, used by the tool reply and the home-world helper."""

    id: str
    name: str
    on: bool
    reachable: bool
    bri: int | None  # percent, None when the lamp cannot be dimmed
    hex: str  # approximate display colour


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=msg, success=False)


def lamp_capabilities(lamp: dict[str, Any]) -> LampCapabilities:
    """What a lamp can do, judged from the fields its state reports."""
    st = lamp.get("state", {})
    return {"dim": "bri" in st, "color": "xy" in st, "ct": "ct" in st}


def _display_hex(state: dict[str, Any], c: LampCapabilities) -> str:
    if c["color"] and state.get("colormode") == "xy":
        return xy_to_hex(state.get("xy", [0.32, 0.33]))
    if c["ct"]:
        return white_hex(state.get("ct", 366))
    return "#ffe2b0"


def lamp_info(lid: str, lamp: dict[str, Any]) -> LampInfo:
    """Short form of one lamp from the bridge's light record."""
    st, c = lamp.get("state", {}), lamp_capabilities(lamp)
    return {
        "id": lid,
        "name": lamp.get("name", "?"),
        "on": bool(st.get("on")),
        "reachable": bool(st.get("reachable", True)),
        "bri": round(st.get("bri", BRI_MAX) / PERCENT_TO_BRI) if c["dim"] else None,
        "hex": _display_hex(st, c),
        **c,
    }


@dataclass(frozen=True)
class LampChange:
    """One change for one lamp; None or "" leaves that part as it is.

    bri is 1-100 %, color a name from COLORS or #rrggbb, kelvin 2000-6500; brightness,
    colour or kelvin also switch the lamp on.
    """

    on: bool | None = None
    bri: float | str | None = None
    color: str = ""
    kelvin: float | str | None = None


def lamp_state_body(change: LampChange) -> dict[str, Any]:
    """The bridge's state body for a change. Raises ValueError for an unknown colour."""
    body: dict[str, Any] = {}
    if change.on is not None:
        body["on"] = bool(change.on)
    if change.bri is not None:
        body["bri"] = max(1, min(BRI_MAX, round(float(change.bri) * PERCENT_TO_BRI)))
    if change.color:
        hx = COLORS.get(change.color.lower().strip(), change.color.strip())
        if not (hx.startswith("#") and len(hx) == 7):
            raise ValueError("unknown colour")
        body["xy"] = hex_to_xy(hx)
    if change.kelvin:
        body["ct"] = kelvin_to_mired(float(change.kelvin))
    if body.keys() & {"bri", "xy", "ct"}:
        body.setdefault("on", True)
    return body


def set_lamp(lid: str, change: LampChange) -> list[dict[str, Any]]:
    """Send one state change to a lamp; return the bridge's per-field success entries.

    Raises ValueError for an unknown colour, hue_bridge.HueBridgeError when the bridge
    refuses, OSError on network trouble.
    """
    return hue_bridge.request("/lights/%s/state" % lid, lamp_state_body(change))


def find_lamp(
    lights: dict[str, dict[str, Any]], name: str, room_ids: set[str] | None = None
) -> str | None:
    """Lamp id for a spoken name: exact, unique partial, then all non-filler words."""
    items = [
        (i, lamp) for i, lamp in lights.items() if room_ids is None or i in room_ids
    ]
    n = name.lower().strip()
    for i, lamp in items:
        if lamp.get("name", "").lower() == n:
            return i
    partial = [i for i, lamp in items if n and n in lamp.get("name", "").lower()]
    if len(partial) == 1:
        return partial[0]
    words = [w for w in n.split() if w not in LAMP_FILLER]
    by_words = [
        i
        for i, lamp in items
        if words and all(w in lamp.get("name", "").lower() for w in words)
    ]
    return by_words[0] if len(by_words) == 1 else None


def _room_lamp_ids(room: str) -> set[str] | None:
    """Lamp ids of the named room, matched like hue_set (None: search all lamps)."""
    if not room:
        return None
    groups = hue_bridge.request("/groups")
    match = hue_bridge.find_room(groups, room)
    return (
        None if match is None else {str(x) for x in groups[match[0]].get("lights", [])}
    )


def _unsupported(lamp: dict[str, Any], color: str, kelvin: Any, bri: Any) -> str:
    """Why the request does not fit this lamp, or "" when it does."""
    c, name = lamp_capabilities(lamp), lamp.get("name")
    if color and not c["color"]:
        return "%s cannot show colours (white lamp)." % name
    if kelvin and not c["ct"]:
        return "%s has no white temperature setting." % name
    if bri is not None and not c["dim"]:
        return "%s cannot be dimmed." % name
    return ""


def _read_back_report(lid: str, reply: Any, want_on: bool | None) -> tuple[str, bool]:
    """Wait, read the lamp back, describe it; ok = reachable and on/off as asked."""
    time.sleep(READ_BACK_DELAY)
    now = lamp_info(lid, hue_bridge.request("/lights/%s" % lid))
    ok = (want_on is None or now["on"] == want_on) and now["reachable"]
    text = "Sent to lamp %s. Bridge reply: %s. Now: %s%s%s. Verified: %s." % (
        now["name"],
        json.dumps(reply)[:200],
        "ON" if now["on"] else "OFF",
        "" if now["bri"] is None else ", %d%%" % now["bri"],
        "" if not now["color"] else ", colour " + now["hex"],
        "YES" if ok else "NO (lamp unreachable?)",
    )
    return text, ok


@ToolRegistry.register(TOOL_NAME)
class HueLightTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
            description=(
                "Control ONE single Philips Hue lamp (not a whole room): switch it"
                " on or off, set brightness 1-100, a colour (red, orange, yellow,"
                " green, cyan, blue, purple, pink, white, warm or #rrggbb; colour"
                " lamps only) or a white temperature in kelvin (2000-6500). Give the"
                " lamp name from hue_light_list; add the room if the "
                "name is not unique. Reports what the lamp reads back."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "light": {
                        "type": "string",
                        "description": "Lamp name, for example Hue Color Desk.",
                    },
                    "room": {
                        "type": "string",
                        "description": "Optional room name to narrow the search.",
                    },
                    "state": {"type": "string", "description": "on or off (optional)"},
                    "brightness": {
                        "type": "integer",
                        "description": "1-100 percent (optional)",
                    },
                    "color": {
                        "type": "string",
                        "description": "Colour name or #rrggbb (optional)",
                    },
                    "kelvin": {
                        "type": "integer",
                        "description": "White temperature 2000-6500 (optional)",
                    },
                },
                "required": ["light"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        hue_bridge.log_call(TOOL_NAME, params)
        want_on = hue_bridge.power_state(params.get("state"))
        if params.get("state") and want_on is None:
            return _fail("state must be on or off.")
        color = params.get("color") or ""
        kelvin, bri = params.get("kelvin"), params.get("brightness")
        try:
            lights = hue_bridge.request("/lights")
            room = str(params.get("room", "") or "").strip()
            lid = find_lamp(
                lights, str(params.get("light", "")).strip(), _room_lamp_ids(room)
            )
            if lid is None:
                names = sorted(lamp.get("name", "?") for lamp in lights.values())
                return _fail(
                    "No such lamp (or not unique). Lamps: %s" % ", ".join(names)
                )
            problem = _unsupported(lights[lid], color, kelvin, bri)
            if problem:
                return _fail(problem)
            reply = set_lamp(lid, LampChange(want_on, bri, color, kelvin))
            text, ok = _read_back_report(lid, reply, want_on)
            return ToolResult(tool_name=TOOL_NAME, content=text, success=ok)
        except Exception as e:  # any bridge/network problem becomes a short tool reply
            return _fail("Hue error: %s" % hue_bridge.error_text(e))
