"""Hue tool: ask the user to approve a room switch in the HUD (approval path).

Pairs with hue_execute. Built and tested but not enabled: the direct hue_set tool is
used instead. It matches rooms exactly like hue_set (hue_bridge.find_room) and never
changes a light itself.
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import hue_bridge
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.approval_store import TIER_HIGH, ApprovalStore

TOOL_NAME = "hue_propose"
# Approval action type and permission key, shared with hue_execute.
HUE_ROOM_POWER = "hue_room_power"


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=msg, success=False)


@ToolRegistry.register(TOOL_NAME)
class HueProposeTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
            description=(
                "Approval mode only: use this instead of hue_set when Hue room"
                " switches must be approved by the user. It does NOT change any"
                " light. It creates a pending request that the user must approve"
                " in the HUD. Never say a request was sent unless this tool"
                " returned a request id. Tell the user the request is waiting"
                " for their approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "room": {
                        "type": "string",
                        "description": "Exact room name, for example Kitchen.",
                    },
                    "state": {
                        "type": "string",
                        "description": "on or off",
                    },
                },
                "required": ["room", "state"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        room = str(params.get("room", "")).strip()
        want_on = hue_bridge.power_state(params.get("state"))
        if want_on is None:
            return _fail("state must be on or off.")
        state = "on" if want_on else "off"
        try:
            gid, name = hue_bridge.lookup_room(room)
            store = ApprovalStore()
            try:
                act = store.queue_action(
                    action_type=HUE_ROOM_POWER,
                    description="Switch Hue room %s %s" % (name, state),
                    payload={"group_id": gid, "room": name, "state": state},
                    permission_key=HUE_ROOM_POWER,
                    tier=TIER_HIGH,
                    ttl_hours=1,
                )
            finally:
                store.close()
            return ToolResult(
                tool_name=TOOL_NAME,
                content=(
                    "Request %s created: switch %s %s. Waiting for the user to"
                    " approve it in the HUD. Nothing has changed yet."
                    % (act.id, name, state)
                ),
                success=True,
            )
        except hue_bridge.UnknownRoom as e:
            return _fail(str(e))
        except Exception as e:
            # A bridge or approvals database problem becomes a short tool reply.
            return _fail("Hue propose error: %s" % hue_bridge.error_text(e))
