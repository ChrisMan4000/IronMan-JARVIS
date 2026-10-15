"""Hue tool: switch ALL Philips Hue rooms on or off and report per room.

Each room is switched, then every light is checked (on/off and reachable).
Reviewed 2026-10-14: comments added, behavior unchanged.
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
    return ToolResult(tool_name="hue_all_set", content=msg, success=False)


def _get(url: str) -> Any:
    """GET a URL from the bridge and decode the JSON."""
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


@ToolRegistry.register("hue_all_set")
class HueAllSetTool(BaseTool):
    tool_id = "hue_all_set"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="hue_all_set",
            description=(
                "ALWAYS call this tool when the user asks to switch ALL"
                " Philips Hue lights, every room or the whole house on or off"
                " (all lights off, everything off). It switches every room,"
                " checks every light and reports per room. Never say all"
                " lights are switched unless this tool returned a result."
                " Report exactly what it returns, including rooms that could"
                " not be confirmed because their lights are unreachable."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "on or off"}
                },
                "required": ["state"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        state = str(params.get("state", "")).strip().lower()
        if state not in ("on", "off"):
            return _fail("state must be on or off.")
        want_on = state == "on"
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
            base = "http://%s/api/%s" % (BRIDGE, key)

            # List all rooms.
            groups = _get(base + "/groups")
            rooms = [
                (gid, g.get("name"), [str(x) for x in g.get("lights", [])])
                for gid, g in groups.items()
                if g.get("type") == "Room"
            ]
            if not rooms:
                return _fail("No rooms found.")

            # Send the command to every room.
            sent = {}
            for gid, name, _ids in rooms:
                try:
                    req = urllib.request.Request(
                        "%s/groups/%s/action" % (base, gid),
                        data=json.dumps({"on": want_on}).encode("utf-8"),
                        method="PUT",
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=5) as r:
                        r.read()
                    sent[gid] = True
                except Exception:
                    sent[gid] = False
            time.sleep(1.0)

            # Check every light and write one line per room.
            lights = _get(base + "/lights")
            lines = []
            n_ok = n_part = n_none = n_bad = 0
            for gid, name, ids in rooms:
                reach = []
                unreach = []
                for lid in ids:
                    li = lights.get(lid, {})
                    if li.get("state", {}).get("reachable", True):
                        reach.append(lid)
                    else:
                        unreach.append(li.get("name", lid))
                if not sent[gid]:
                    n_bad += 1
                    lines.append("%s: FAILED, the bridge did not accept the command" % name)
                elif not reach:
                    n_none += 1
                    lines.append(
                        "%s: NOT CONFIRMABLE, all lights unreachable (%s)"
                        % (name, ", ".join(unreach))
                    )
                else:
                    match = all(
                        bool(lights[lid].get("state", {}).get("on")) == want_on
                        for lid in reach
                    )
                    if not match:
                        n_bad += 1
                        lines.append("%s: MISMATCH, a reachable light is not %s" % (name, state))
                    elif unreach:
                        n_part += 1
                        lines.append(
                            "%s: confirmed %s for the reachable lights; unreachable: %s"
                            % (name, state, ", ".join(unreach))
                        )
                    else:
                        n_ok += 1
                        lines.append("%s: verified %s" % (name, state))
            head = (
                "Requested all rooms %s. %d verified, %d partly (some lights unreachable),"
                " %d not confirmable (all lights unreachable), %d failed."
                % (state, n_ok, n_part, n_none, n_bad)
            )
            return ToolResult(
                tool_name="hue_all_set",
                content=head + "\n" + "\n".join(lines),
                success=(n_bad == 0),
            )
        except Exception as e:
            return _fail("Hue all set error: %s" % type(e).__name__)
