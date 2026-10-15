from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.tools.approval_store import (
    STATUS_APPROVED,
    STATUS_EXECUTED,
    ApprovalStore,
)

BRIDGE = os.environ.get("HUE_BRIDGE_IP", "").strip()  # your Hue bridge IP, see README
KEY_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "hue-key.txt")


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name="hue_execute", content=msg, success=False)


@ToolRegistry.register("hue_execute")
class HueExecuteTool(BaseTool):
    tool_id = "hue_execute"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="hue_execute",
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
        rid = str(params.get("request_id", "")).strip()
        if not rid:
            return _fail("No request id given.")
        try:
            store = ApprovalStore()
            try:
                act = store.get_action(rid)
                if act is None:
                    return _fail("Request %s not found." % rid)
                if act.action_type != "hue_room_power":
                    return _fail("Request %s is not a Hue request." % rid)
                if act.status != STATUS_APPROVED:
                    return _fail(
                        "Request %s is %s, not approved by the user. Nothing was changed."
                        % (rid, act.status)
                    )
                exp = datetime.fromisoformat(act.expires_at)
                if exp < datetime.now(timezone.utc):
                    return _fail("Request %s has expired. Nothing was changed." % rid)
                gid = str(act.payload.get("group_id"))
                room = act.payload.get("room")
                want_on = act.payload.get("state") == "on"
                with open(KEY_FILE, "r", encoding="utf-8") as f:
                    key = f.read().strip()
                base = "http://%s/api/%s/groups/%s" % (BRIDGE, key, gid)
                req = urllib.request.Request(
                    base + "/action",
                    data=json.dumps({"on": want_on}).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    reply = json.loads(r.read().decode("utf-8"))
                store.update_status(rid, STATUS_EXECUTED)
                time.sleep(1.0)
                with urllib.request.urlopen(base, timeout=5) as r:
                    grp = json.loads(r.read().decode("utf-8"))
                any_on = bool(grp.get("state", {}).get("any_on"))
                ok = any_on == want_on
                text = "Sent: %s %s. Bridge reply: %s. Verified by reading back: %s (any light on now: %s)." % (
                    room,
                    "on" if want_on else "off",
                    json.dumps(reply),
                    "YES" if ok else "NO, state does not match",
                    any_on,
                )
                return ToolResult(tool_name="hue_execute", content=text, success=ok)
            finally:
                store.close()
        except Exception as e:
            return _fail("Hue execute error: %s" % type(e).__name__)