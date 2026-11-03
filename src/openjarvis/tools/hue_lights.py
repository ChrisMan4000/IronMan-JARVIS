"""Hue tool (read-only): list the Philips Hue rooms and which of their lights are on."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import hue_bridge
from openjarvis.tools._stubs import BaseTool, ToolSpec

TOOL_NAME = "hue_lights"


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=msg, success=False)


def _light_label(light_id: Any, lights: dict[str, dict[str, Any]]) -> str:
    light = lights.get(str(light_id), {})
    state = light.get("state", {})
    flag = "on" if state.get("on") else "off"
    if not state.get("reachable", True):
        flag += ", unreachable"
    return "%s (%s)" % (light.get("name", light_id), flag)


def room_report(
    groups: dict[str, dict[str, Any]], lights: dict[str, dict[str, Any]]
) -> str:
    """One line per room: name, ON/off and each light's own state."""
    lines = []
    for g in groups.values():
        if g.get("type") != "Room":
            continue
        labels = [_light_label(lid, lights) for lid in g.get("lights", [])]
        any_on = g.get("state", {}).get("any_on")
        lines.append(
            "%s: %s - %s"
            % (g.get("name"), "ON" if any_on else "off", "; ".join(labels))
        )
    return "\n".join(lines)


@ToolRegistry.register(TOOL_NAME)
class HueLightsTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
            description=(
                "ALWAYS call this tool, never hue_light_list, when the user asks"
                " about rooms, says hue_lights, or asks which rooms or lights are"
                " on or off. Read-only. Lists the user's Philips Hue rooms and"
                " whether"
                " their lights are on or off. Use it for questions like"
                " 'which lights are on?'. It cannot change anything."
            ),
            parameters={"type": "object", "properties": {}},
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            report = room_report(
                hue_bridge.request("/groups"), hue_bridge.request("/lights")
            )
        except Exception as e:  # any bridge/network problem becomes a short tool reply
            return _fail("Hue bridge error: %s" % hue_bridge.error_text(e))
        return ToolResult(tool_name=TOOL_NAME, content=report, success=True)
