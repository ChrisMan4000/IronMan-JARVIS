"""Hue tool: control ONE Philips Hue lamp (not a whole room).

What it can do per lamp: on/off, brightness 1-100 %, a colour (name or #hex, only on
colour lamps) and a white temperature in kelvin (only on lamps with white tones).
It reads the lamp back after 0.6 s and reports "Verified: YES/NO".
Lamp names are the ones from the Hue app (hue_light_list shows them).
The lamp helpers here (lamp_info, set_lamp, find_lamp) are also used by the local
home-world helper.
"""

from __future__ import annotations

import json
import time
from typing import Any, TypedDict

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import hue_bridge
from openjarvis.tools._stubs import BaseTool, ToolSpec

TOOL_NAME = "hue_light"
COLORS = {
    "red": "#ff2a1a",
    "orange": "#ff8a1a",
    "yellow": "#ffd21a",
    "green": "#2aff4a",
    "cyan": "#1affe8",
    "blue": "#1a4aff",
    "purple": "#8a2aff",
    "violet": "#8a2aff",
    "pink": "#ff4ab4",
    "magenta": "#ff1aff",
    "white": "#ffffff",
    "warm": "#ffd6a0",
    "warm white": "#ffd6a0",
}
LAMP_FILLER = ("the", "light", "lights", "lamp", "lamps", "hue", "my", "in", "on", "at")
READ_BACK_DELAY = 0.6  # seconds before a single lamp reports its new state


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


def _srgb_to_linear(c: float) -> float:
    return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92


def _linear_to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_xy(h: str) -> list[float]:
    """#rrggbb -> CIE xy as the Hue bridge expects it (black gives neutral white)."""
    h = h.lstrip("#")
    r, g, b = (_srgb_to_linear(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4))
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    s = x + y + z
    return [round(x / s, 4), round(y / s, 4)] if s > 0 else [0.3227, 0.329]


def xy_to_hex(xy: list[float]) -> str:
    """CIE xy -> #rrggbb at full brightness, for showing a lamp's colour."""
    x, y = xy
    if y <= 0:
        return "#ffffff"
    big_y = 1.0
    big_x, big_z = big_y / y * x, big_y / y * (1 - x - y)
    r = big_x * 1.656492 - big_y * 0.354851 - big_z * 0.255038
    g = -big_x * 0.707196 + big_y * 1.655397 + big_z * 0.036152
    b = big_x * 0.051713 - big_y * 0.121364 + big_z * 1.011530
    m = max(r, g, b, 1e-6)
    return "#" + "".join(
        "%02x" % int(max(0.0, min(1.0, _linear_to_srgb(max(0.0, c / m)))) * 255)
        for c in (r, g, b)
    )


def lamp_capabilities(lamp: dict[str, Any]) -> LampCapabilities:
    """What a lamp can do, judged from the fields its state reports."""
    st = lamp.get("state", {})
    return {"dim": "bri" in st, "color": "xy" in st, "ct": "ct" in st}


def _display_hex(state: dict[str, Any], c: LampCapabilities) -> str:
    if c["color"] and state.get("colormode") == "xy":
        return xy_to_hex(state.get("xy", [0.32, 0.33]))
    if c["ct"]:
        kelvin = 1e6 / max(153, state.get("ct", 366))
        return (
            "#ffd6a0" if kelvin < 3200 else ("#fff1dc" if kelvin < 4800 else "#e8f0ff")
        )
    return "#ffe2b0"


def lamp_info(lid: str, lamp: dict[str, Any]) -> LampInfo:
    """Short form of one lamp from the bridge's light record."""
    st, c = lamp.get("state", {}), lamp_capabilities(lamp)
    return {
        "id": lid,
        "name": lamp.get("name", "?"),
        "on": bool(st.get("on")),
        "reachable": bool(st.get("reachable", True)),
        "bri": round(st.get("bri", 254) / 2.54) if c["dim"] else None,
        "hex": _display_hex(st, c),
        **c,
    }


def set_lamp(
    lid: str,
    on: bool | None = None,
    bri: float | str | None = None,
    color: str = "",
    kelvin: float | str | None = None,
) -> list[dict[str, Any]]:
    """Send one state change to a lamp; return the bridge's per-field success entries.

    bri is 1-100 %, color a name from COLORS or #rrggbb, kelvin 2000-6500; brightness,
    colour or kelvin also switch the lamp on. Raises ValueError for an unknown colour,
    hue_bridge.HueBridgeError when the bridge refuses, OSError on network trouble.
    """
    body: dict[str, Any] = {}
    if on is not None:
        body["on"] = bool(on)
    if bri is not None:
        body["bri"] = max(1, min(254, round(float(bri) * 2.54)))
        body.setdefault("on", True)
    if color:
        hx = COLORS.get(color.lower().strip(), color.strip())
        if not (hx.startswith("#") and len(hx) == 7):
            raise ValueError("unknown colour")
        body["xy"] = hex_to_xy(hx)
        body.setdefault("on", True)
    if kelvin:
        body["ct"] = max(153, min(500, round(1e6 / float(kelvin))))
        body.setdefault("on", True)
    return hue_bridge.request("/lights/%s/state" % lid, body)


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
        name = str(params.get("light", "")).strip()
        state = str(params.get("state", "") or "").strip().lower()
        if state and state not in ("on", "off"):
            return _fail("state must be on or off.")
        color, kelvin, bri = (
            params.get("color") or "",
            params.get("kelvin"),
            params.get("brightness"),
        )
        try:
            lights = hue_bridge.request("/lights")
            lid = find_lamp(
                lights, name, _room_lamp_ids(str(params.get("room", "") or "").strip())
            )
            if lid is None:
                names = sorted(lamp.get("name", "?") for lamp in lights.values())
                return _fail(
                    "No such lamp (or not unique). Lamps: %s" % ", ".join(names)
                )
            problem = _unsupported(lights[lid], color, kelvin, bri)
            if problem:
                return _fail(problem)
            reply = set_lamp(
                lid, None if not state else state == "on", bri, color, kelvin
            )
            time.sleep(READ_BACK_DELAY)
            now = lamp_info(lid, hue_bridge.request("/lights/%s" % lid))
            ok = (not state or now["on"] == (state == "on")) and now["reachable"]
            text = "Sent to lamp %s. Bridge reply: %s. Now: %s%s%s. Verified: %s." % (
                now["name"],
                json.dumps(reply)[:200],
                "ON" if now["on"] else "OFF",
                "" if now["bri"] is None else ", %d%%" % now["bri"],
                "" if not now["color"] else ", colour " + now["hex"],
                "YES" if ok else "NO (lamp unreachable?)",
            )
            return ToolResult(tool_name=TOOL_NAME, content=text, success=ok)
        except Exception as e:  # any bridge/network problem becomes a short tool reply
            return _fail("Hue error: %s" % hue_bridge.error_text(e))
