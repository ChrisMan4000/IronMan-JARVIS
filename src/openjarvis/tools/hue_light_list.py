"""Hue tool (read-only): list every single Philips Hue light with id, state and brightness.

Reviewed 2026-10-14: comments added, behavior unchanged.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

# Bridge address and the file with the app key (never print or share the key)
BRIDGE = os.environ.get("HUE_BRIDGE_IP", "").strip()  # your Hue bridge IP, see README
KEY_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "hue-key.txt")


@ToolRegistry.register("hue_light_list")
class HueLightListTool(BaseTool):
    tool_id = "hue_light_list"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="hue_light_list",
            description=(
                "Read-only. Lists every single Philips Hue light one by one"
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
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
            url = "http://%s/api/%s/lights" % (BRIDGE, key)
            with urllib.request.urlopen(url, timeout=5) as r:
                lights = json.loads(r.read().decode("utf-8"))

            # One line per light: id, name, on/off, brightness, reachable.
            lines = []
            for lid in sorted(lights, key=lambda x: int(x)):
                li = lights[lid]
                st = li.get("state", {})
                text = "id %s: %s - %s" % (
                    lid,
                    li.get("name", "?"),
                    "ON" if st.get("on") else "off",
                )
                if st.get("on") and "bri" in st:
                    text += " at %d%%" % round(st["bri"] * 100 / 254)
                if not st.get("reachable", True):
                    text += " (unreachable)"
                lines.append(text)
            return ToolResult(
                tool_name="hue_light_list", content="\n".join(lines), success=True
            )
        except Exception as e:
            return ToolResult(
                tool_name="hue_light_list",
                content="Hue bridge error: %s" % type(e).__name__,
                success=False,
            )
