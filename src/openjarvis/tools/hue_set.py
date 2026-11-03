"""Hue tool: switch ONE Philips Hue room on or off right away, then read the state back.

This is the direct path the model and the HUD /hue route use. hue_propose and
hue_execute are the approval-gated alternative, kept for later and not enabled.
Room matching rules live in hue_bridge.find_room.
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import hue_bridge
from openjarvis.tools._stubs import BaseTool, ToolSpec

TOOL_NAME = "hue_set"


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=msg, success=False)


@ToolRegistry.register(TOOL_NAME)
class HueSetTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
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
        hue_bridge.log_call(TOOL_NAME, params)
        room = str(params.get("room", "")).strip()
        want_on = hue_bridge.power_state(params.get("state"))
        if want_on is None:
            return _fail("state must be on or off.")
        try:
            gid, name = hue_bridge.lookup_room(room)
            reply = hue_bridge.set_room_power(gid, want_on)
            text, ok = hue_bridge.read_back_report(gid, name, want_on, reply)
            return ToolResult(tool_name=TOOL_NAME, content=text, success=ok)
        except hue_bridge.UnknownRoom as e:
            return _fail(str(e))
        except Exception as e:  # any bridge/network problem becomes a short tool reply
            return _fail("Hue set error: %s" % hue_bridge.error_text(e))
