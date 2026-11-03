"""Hue tool: switch ALL Philips Hue rooms on or off and report per room.

Each room is switched, then every light is checked on its own (on/off and reachable),
because a room's any_on read-back can look right while all its lights are unreachable.
"""

from __future__ import annotations

import time
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import hue_bridge
from openjarvis.tools._stubs import BaseTool, ToolSpec

TOOL_NAME = "hue_all_set"

# Per-room verdicts, in the order the summary line counts them.
VERIFIED, PARTLY, UNCONFIRMABLE, FAILED = (
    "verified",
    "partly",
    "unconfirmable",
    "failed",
)


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=msg, success=False)


def room_verdict(
    name: str,
    light_ids: list[str],
    lights: dict[str, dict[str, Any]],
    sent: bool,
    want_on: bool,
) -> tuple[str, str]:
    """(verdict, report line) for one room after the switch command."""
    state = "on" if want_on else "off"
    if not sent:
        return FAILED, "%s: FAILED, the bridge did not accept the command" % name
    reachable, unreachable = [], []
    for lid in light_ids:
        light = lights.get(lid)
        if light is not None and light.get("state", {}).get("reachable", True):
            reachable.append(light)
        else:  # unreachable, or missing from the bridge's light list
            unreachable.append(light.get("name", lid) if light else lid)
    if not reachable:
        return UNCONFIRMABLE, "%s: NOT CONFIRMABLE, all lights unreachable (%s)" % (
            name,
            ", ".join(unreachable),
        )
    if not all(
        bool(light.get("state", {}).get("on")) == want_on for light in reachable
    ):
        return FAILED, "%s: MISMATCH, a reachable light is not %s" % (name, state)
    if unreachable:
        return PARTLY, "%s: confirmed %s for the reachable lights; unreachable: %s" % (
            name,
            state,
            ", ".join(unreachable),
        )
    return VERIFIED, "%s: verified %s" % (name, state)


@ToolRegistry.register(TOOL_NAME)
class HueAllSetTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
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
                "properties": {"state": {"type": "string", "description": "on or off"}},
                "required": ["state"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        hue_bridge.log_call(TOOL_NAME, params)
        want_on = hue_bridge.power_state(params.get("state"))
        if want_on is None:
            return _fail("state must be on or off.")
        state = "on" if want_on else "off"
        try:
            groups = hue_bridge.request("/groups")
            rooms = [
                (gid, g.get("name"), [str(x) for x in g.get("lights", [])])
                for gid, g in groups.items()
                if g.get("type") == "Room"
            ]
            if not rooms:
                return _fail("No rooms found.")
            sent = {}
            for gid, _name, _ids in rooms:
                try:
                    hue_bridge.set_room_power(gid, want_on)
                    sent[gid] = True
                except Exception:
                    # A refused room is reported as FAILED; the others still switch.
                    sent[gid] = False
            time.sleep(hue_bridge.READ_BACK_DELAY)
            lights = hue_bridge.request("/lights")
            verdicts = [
                room_verdict(name, ids, lights, sent[gid], want_on)
                for gid, name, ids in rooms
            ]
            count = {
                v: sum(1 for verdict, _line in verdicts if verdict == v)
                for v in (VERIFIED, PARTLY, UNCONFIRMABLE, FAILED)
            }
            head = (
                "Requested all rooms %s. %d verified, %d partly (some lights"
                " unreachable), %d not confirmable (all lights unreachable),"
                " %d failed."
                % (
                    state,
                    count[VERIFIED],
                    count[PARTLY],
                    count[UNCONFIRMABLE],
                    count[FAILED],
                )
            )
            return ToolResult(
                tool_name=TOOL_NAME,
                content=head + "\n" + "\n".join(line for _verdict, line in verdicts),
                success=(count[FAILED] == 0),
            )
        except Exception as e:  # any bridge/network problem becomes a short tool reply
            return _fail("Hue all set error: %s" % hue_bridge.error_text(e))
