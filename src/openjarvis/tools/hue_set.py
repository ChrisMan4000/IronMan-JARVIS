"""Hue tool: switch ONE Philips Hue room on or off, then read the state back.

Matching: exact room name, else a unique partial name, else the phrase without
filler words (the, light, lamp, room). Reviewed 2026-10-14: comments added and
the call log line is cut to 300 characters.
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

# Bridge address and the file with the app key (never print or share the key)
BRIDGE = os.environ.get("HUE_BRIDGE_IP", "").strip()  # your Hue bridge IP, see README
KEY_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "hue-key.txt")


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name="hue_set", content=msg, success=False)


@ToolRegistry.register("hue_set")
class HueSetTool(BaseTool):
    tool_id = "hue_set"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="hue_set",
            description=(
                "ALWAYS call this tool when the user asks to switch a Philips"
                " Hue room on or off (turn off kitchen, lights on in the"
                " office). It acts immediately and reads the state back."
                " Never say the lights were switched unless this tool"
                " returned a result. Report exactly what it returns."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "room": {
                        "type": "string",
                        "description": "Exact room name, for example Kitchen.",
                    },
                    "state": {"type": "string", "description": "on or off"},
                },
                "required": ["room", "state"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        # Log every call (shortened) so you can see what was asked.
        try:
            with open(os.path.join(os.path.expanduser("~"), ".openjarvis", "hue-set-log.txt"), "a", encoding="utf-8") as _lf:
                _lf.write("%s %s\n" % (time.strftime("%H:%M:%S"), repr(params)[:300]))
        except Exception:
            pass
        room = str(params.get("room", "")).strip()
        state = str(params.get("state", "")).strip().lower()
        if state not in ("on", "off"):
            return _fail("state must be on or off.")
        want_on = state == "on"
        if len(room) > 3 and room.lower().endswith("s"):
            room = room[:-1]
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
            root = "http://%s/api/%s/groups" % (BRIDGE, key)
            with urllib.request.urlopen(root, timeout=5) as r:
                groups = json.loads(r.read().decode("utf-8"))

            # Find the room: exact, then unique partial, then phrase without filler words.
            match = None
            for gid, g in groups.items():
                if g.get("type") == "Room" and g.get("name", "").lower() == room.lower():
                    match = (gid, g.get("name"))
                    break
            if match is None and room:
                cands = [(gid, g.get("name")) for gid, g in groups.items() if g.get("type") == "Room" and room.lower() in g.get("name", "").lower()]
                if len(cands) == 1:
                    match = cands[0]
            if match is None and room:
                cleaned = " ".join(w for w in room.lower().split() if w not in ("the", "light", "lights", "lamp", "lamps", "room"))
                cands2 = [(gid, g.get("name")) for gid, g in groups.items() if g.get("type") == "Room" and g.get("name", "").lower() in (cleaned, cleaned[:-1])]
                if len(cands2) == 1:
                    match = cands2[0]
            if match is None:
                names = [g.get("name") for g in groups.values() if g.get("type") == "Room"]
                return _fail("No such room. Rooms: %s" % ", ".join(names))

            # Switch the room, wait 1 s, read it back.
            base = "%s/%s" % (root, match[0])
            req = urllib.request.Request(
                base + "/action",
                data=json.dumps({"on": want_on}).encode("utf-8"),
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                reply = json.loads(r.read().decode("utf-8"))
            time.sleep(1.0)
            with urllib.request.urlopen(base, timeout=5) as r:
                grp = json.loads(r.read().decode("utf-8"))
            any_on = bool(grp.get("state", {}).get("any_on"))
            ok = any_on == want_on
            text = "Sent: %s %s. Bridge reply: %s. Verified by reading back: %s (any light on now: %s)." % (
                match[1],
                state,
                json.dumps(reply),
                "YES" if ok else "NO (some lights in this room may be unreachable)",
                any_on,
            )
            return ToolResult(tool_name="hue_set", content=text, success=ok)
        except Exception as e:
            return _fail("Hue set error: %s" % type(e).__name__)
