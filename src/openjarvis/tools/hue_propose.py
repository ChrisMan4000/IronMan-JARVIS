from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.approval_store import TIER_HIGH, ApprovalStore

BRIDGE = os.environ.get("HUE_BRIDGE_IP", "").strip()  # your Hue bridge IP, see README
KEY_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "hue-key.txt")


@ToolRegistry.register("hue_propose")
class HueProposeTool(BaseTool):
    tool_id = "hue_propose"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="hue_propose",
            description=(
                "ALWAYS call this tool when the user asks to switch a Philips Hue room on or off (turn off kitchen, lights on in the office). Never say a request was sent unless this tool returned a request id. It does NOT"
                " change any light. It creates a pending request that the user"
                " must approve in the HUD. Tell the user the request is waiting"
                " for their approval. Use the exact room name."
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
        state = str(params.get("state", "")).strip().lower()
        if state not in ("on", "off"):
            return ToolResult(
                tool_name="hue_propose",
                content="state must be on or off.",
                success=False,
            )
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
            url = "http://%s/api/%s/groups" % (BRIDGE, key)
            with urllib.request.urlopen(url, timeout=5) as r:
                groups = json.loads(r.read().decode("utf-8"))
            match = None
            for gid, g in groups.items():
                if g.get("type") == "Room" and g.get("name", "").lower() == room.lower():
                    match = (gid, g.get("name"))
                    break
            if match is None:
                names = [g.get("name") for g in groups.values() if g.get("type") == "Room"]
                return ToolResult(
                    tool_name="hue_propose",
                    content="No such room. Rooms: %s" % ", ".join(names),
                    success=False,
                )
            store = ApprovalStore()
            try:
                act = store.queue_action(
                    action_type="hue_room_power",
                    description="Switch Hue room %s %s" % (match[1], state),
                    payload={"group_id": match[0], "room": match[1], "state": state},
                    permission_key="hue_room_power",
                    tier=TIER_HIGH,
                    ttl_hours=1,
                )
            finally:
                store.close()
            return ToolResult(
                tool_name="hue_propose",
                content="Request %s created: switch %s %s. Waiting for the user to approve it in the HUD. Nothing has changed yet." % (act.id, match[1], state),
                success=True,
            )
        except Exception as e:
            return ToolResult(
                tool_name="hue_propose",
                content="Hue propose error: %s" % type(e).__name__,
                success=False,
            )