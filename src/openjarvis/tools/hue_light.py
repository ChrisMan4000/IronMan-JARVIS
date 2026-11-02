"""Hue tool: control ONE Philips Hue lamp (not a whole room).

What it can do per lamp: on/off, brightness 1-100 %, a colour (name or #hex, only on
colour lamps) and a white temperature in kelvin (only on lamps with white tones).
It reads the lamp back after 0.6 s and reports "Verified: YES/NO".
Lamp names are the ones from the Hue app (hue_light_list shows them).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.hue_set import BRIDGE, KEY_FILE

COLORS = {"red": "#ff2a1a", "orange": "#ff8a1a", "yellow": "#ffd21a", "green": "#2aff4a", "cyan": "#1affe8",
          "blue": "#1a4aff", "purple": "#8a2aff", "violet": "#8a2aff", "pink": "#ff4ab4", "magenta": "#ff1aff",
          "white": "#ffffff", "warm": "#ffd6a0", "warm white": "#ffd6a0"}
FILLER = ("the", "light", "lights", "lamp", "lamps", "hue", "my", "in", "on", "at")


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name="hue_light", content=msg, success=False)


def bridge() -> str:
    """Bridge IP from the environment, else from the Windows user settings."""
    b = BRIDGE
    if not b:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                b = str(winreg.QueryValueEx(k, "HUE_BRIDGE_IP")[0]).strip()
        except Exception:
            b = ""
    return b


def api(path: str, body: Any = None) -> Any:
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        key = f.read().strip()
    b = bridge()
    if not b:
        raise RuntimeError("no bridge address")
    req = urllib.request.Request("http://%s/api/%s%s" % (b, key, path),
                                 data=None if body is None else json.dumps(body).encode("utf-8"),
                                 method="GET" if body is None else "PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def hex_to_xy(h: str) -> list:
    h = h.lstrip("#")
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = lambda c: ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92  # noqa: E731
    r, g, b = lin(r), lin(g), lin(b)
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    s = x + y + z
    return [round(x / s, 4), round(y / s, 4)] if s > 0 else [0.3227, 0.329]


def xy_to_hex(xy: list, bri: int = 254) -> str:
    x, y = xy
    if y <= 0:
        return "#ffffff"
    Y = 1.0
    X, Z = Y / y * x, Y / y * (1 - x - y)
    r = X * 1.656492 - Y * 0.354851 - Z * 0.255038
    g = -X * 0.707196 + Y * 1.655397 + Z * 0.036152
    b = X * 0.051713 - Y * 0.121364 + Z * 1.011530
    m = max(r, g, b, 1e-6)
    gam = lambda c: 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055  # noqa: E731
    return "#" + "".join("%02x" % int(max(0, min(1, gam(max(0, c / m)))) * 255) for c in (r, g, b))


def caps(lamp: dict) -> dict:
    st = lamp.get("state", {})
    return {"dim": "bri" in st, "color": "xy" in st, "ct": "ct" in st}


def lamp_info(lid: str, lamp: dict) -> dict:
    """Short form used by the helper and the reports."""
    st, c = lamp.get("state", {}), caps(lamp)
    if c["color"] and st.get("colormode") == "xy":
        hx = xy_to_hex(st.get("xy", [0.32, 0.33]))
    elif c["ct"]:
        k = 1e6 / max(153, st.get("ct", 366))
        hx = "#ffd6a0" if k < 3200 else ("#fff1dc" if k < 4800 else "#e8f0ff")
    else:
        hx = "#ffe2b0"
    return {"id": lid, "name": lamp.get("name", "?"), "on": bool(st.get("on")), "reachable": bool(st.get("reachable", True)),
            "bri": round(st.get("bri", 254) / 2.54) if c["dim"] else None, "hex": hx, **c}


def set_lamp(lid: str, on: Any = None, bri: Any = None, color: str = "", kelvin: Any = None) -> Any:
    body: dict = {}
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
    return api("/lights/%s/state" % lid, body)


def find_lamp(lights: dict, name: str, room_ids: Any = None) -> Any:
    items = [(i, l) for i, l in lights.items() if room_ids is None or i in room_ids]
    n = name.lower().strip()
    for i, l in items:
        if l.get("name", "").lower() == n:
            return i
    c = [i for i, l in items if n and n in l.get("name", "").lower()]
    if len(c) == 1:
        return c[0]
    words = [w for w in n.split() if w not in FILLER]
    c = [i for i, l in items if words and all(w in l.get("name", "").lower() for w in words)]
    return c[0] if len(c) == 1 else None


@ToolRegistry.register("hue_light")
class HueLightTool(BaseTool):
    tool_id = "hue_light"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="hue_light",
            description=(
                "Control ONE single Philips Hue lamp (not a whole room): switch it on or off, set brightness 1-100, "
                "a colour (red, orange, yellow, green, cyan, blue, purple, pink, white, warm or #rrggbb; colour lamps only) "
                "or a white temperature in kelvin (2000-6500). Give the lamp name from hue_light_list; add the room if the "
                "name is not unique. Reports what the lamp reads back."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "light": {"type": "string", "description": "Lamp name, for example Hue Color Desk."},
                    "room": {"type": "string", "description": "Optional room name to narrow the search."},
                    "state": {"type": "string", "description": "on or off (optional)"},
                    "brightness": {"type": "integer", "description": "1-100 percent (optional)"},
                    "color": {"type": "string", "description": "Colour name or #rrggbb (optional)"},
                    "kelvin": {"type": "integer", "description": "White temperature 2000-6500 (optional)"},
                },
                "required": ["light"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            with open(os.path.join(os.path.expanduser("~"), ".openjarvis", "hue-set-log.txt"), "a", encoding="utf-8") as lf:
                lf.write("%s light %s\n" % (time.strftime("%H:%M:%S"), repr(params)[:300]))
        except Exception:
            pass
        name = str(params.get("light", "")).strip()
        state = str(params.get("state", "") or "").strip().lower()
        if state and state not in ("on", "off"):
            return _fail("state must be on or off.")
        try:
            lights = api("/lights")
            room_ids = None
            room = str(params.get("room", "") or "").strip().lower()
            if room:
                for g in api("/groups").values():
                    if g.get("type") == "Room" and room in g.get("name", "").lower():
                        room_ids = set(g.get("lights", []))
            lid = find_lamp(lights, name, room_ids)
            if lid is None:
                return _fail("No such lamp (or not unique). Lamps: %s" % ", ".join(sorted(l.get("name", "?") for l in lights.values())))
            c = caps(lights[lid])
            color, kelvin, bri = params.get("color") or "", params.get("kelvin"), params.get("brightness")
            if color and not c["color"]:
                return _fail("%s cannot show colours (white lamp)." % lights[lid].get("name"))
            if kelvin and not c["ct"]:
                return _fail("%s has no white temperature setting." % lights[lid].get("name"))
            if bri is not None and not c["dim"]:
                return _fail("%s cannot be dimmed." % lights[lid].get("name"))
            reply = set_lamp(lid, None if not state else state == "on", bri, color, kelvin)
            time.sleep(0.6)
            now = lamp_info(lid, api("/lights/%s" % lid))
            ok = (not state or now["on"] == (state == "on")) and now["reachable"]
            text = "Sent to lamp %s. Bridge reply: %s. Now: %s%s%s. Verified: %s." % (
                now["name"], json.dumps(reply)[:200], "ON" if now["on"] else "OFF",
                "" if now["bri"] is None else ", %d%%" % now["bri"], "" if not c["color"] else ", colour " + now["hex"],
                "YES" if ok else "NO (lamp unreachable?)")
            return ToolResult(tool_name="hue_light", content=text, success=ok)
        except Exception as e:
            return _fail("Hue error: %s" % type(e).__name__)
