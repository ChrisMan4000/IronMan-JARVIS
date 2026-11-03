"""Hue tool (read-only): list every Philips Hue lamp with id, state and brightness."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools import hue_bridge
from openjarvis.tools._stubs import BaseTool, ToolSpec

TOOL_NAME = "hue_light_list"


def _fail(msg: str) -> ToolResult:
    return ToolResult(tool_name=TOOL_NAME, content=msg, success=False)


def _id_order(light_id: str) -> tuple[int, str]:
    """Numeric ids first, in number order; any other id after them (never a crash)."""
    return (int(light_id), "") if light_id.isdigit() else (1 << 30, light_id)


def lamp_report(lights: dict[str, dict[str, Any]]) -> str:
    """One line per lamp: id, name, ON/off, brightness when on, unreachable flag."""
    lines = []
    for lid in sorted(lights, key=_id_order):
        light = lights[lid]
        state = light.get("state", {})
        text = "id %s: %s - %s" % (
            lid,
            light.get("name", "?"),
            "ON" if state.get("on") else "off",
        )
        if state.get("on") and "bri" in state:
            text += " at %d%%" % round(state["bri"] * 100 / 254)
        if not state.get("reachable", True):
            text += " (unreachable)"
        lines.append(text)
    return "\n".join(lines)


@ToolRegistry.register(TOOL_NAME)
class HueLightListTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
            description=(
                "Use this ONLY for one individual light or lamp, never when the user"
                " asks about rooms or says hue_lights. Read-only. Lists every single"
                " Philips Hue light one by one"
                " with its id, name, on or off, whether it is reachable and"
                " its brightness in percent. Use it when the user asks about"
                " an individual light or lamp, or wants every light listed."
                " It cannot change anything."
            ),
            parameters={"type": "object", "properties": {}},
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            report = lamp_report(hue_bridge.request("/lights"))
        except Exception as e:  # any bridge/network problem becomes a short tool reply
            return _fail("Hue bridge error: %s" % hue_bridge.error_text(e))
        return ToolResult(tool_name=TOOL_NAME, content=report, success=True)
