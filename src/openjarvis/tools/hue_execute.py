"""Hue tool: carry out a room switch that the user approved in the HUD (approval path).

Pairs with hue_propose. Built and tested but not enabled: the direct hue_set tool is
used instead. To switch the approval path on, enable hue_propose and hue_execute and
remove hue_set from the enabled tools.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import hue_bridge
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.approval_store import (
    STATUS_APPROVED,
    STATUS_EXECUTED,
    ApprovalStore,
    PendingAction,
)
from openjarvis.tools.hue_propose import HUE_ROOM_POWER

TOOL_NAME = "hue_execute"


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=msg, success=False)


def _approved_action(
    store: ApprovalStore, rid: str
) -> tuple[PendingAction | None, str]:
    """(action, "") for an approved, unexpired Hue request, else (None, reason)."""
    act = store.get_action(rid)
    if act is None:
        return None, "Request %s not found." % rid
    if act.action_type != HUE_ROOM_POWER:
        return None, "Request %s is not a Hue request." % rid
    if act.status != STATUS_APPROVED:
        return (
            None,
            "Request %s is %s, not approved by the user. Nothing was changed."
            % (rid, act.status),
        )
    if datetime.fromisoformat(act.expires_at) < datetime.now(timezone.utc):
        return None, "Request %s has expired. Nothing was changed." % rid
    return act, ""


@ToolRegistry.register(TOOL_NAME)
class HueExecuteTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
            description=(
                "Carries out a Hue room request that the USER has already"
                " approved in the HUD. Give the request id returned by"
                " hue_propose. It refuses if the user has not approved it."
                " Report exactly what the tool returns."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "Request id from hue_propose.",
                    }
                },
                "required": ["request_id"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        hue_bridge.log_call(TOOL_NAME, params)
        rid = str(params.get("request_id", "")).strip()
        if not rid:
            return _fail("No request id given.")
        try:
            store = ApprovalStore()
        except Exception as e:  # approvals database missing or locked
            return _fail("Hue execute error: %s" % type(e).__name__)
        try:
            act, refusal = _approved_action(store, rid)
            if act is None:
                return _fail(refusal)
            gid = str(act.payload.get("group_id"))
            room = str(act.payload.get("room"))
            want_on = act.payload.get("state") == "on"
            try:
                reply = hue_bridge.set_room_power(gid, want_on)
            except Exception as e:  # nothing was switched
                return _fail("Hue execute error: %s" % hue_bridge.error_text(e))
            store.update_status(rid, STATUS_EXECUTED)  # sent: never replay this request
            try:
                text, ok = hue_bridge.read_back_report(gid, room, want_on, reply)
            except Exception as e:  # sent, but the state could not be confirmed
                return _fail(
                    "Sent: %s %s. Could not read back (%s)."
                    % (room, "on" if want_on else "off", hue_bridge.error_text(e))
                )
            return ToolResult(tool_name=TOOL_NAME, content=text, success=ok)
        finally:
            store.close()
