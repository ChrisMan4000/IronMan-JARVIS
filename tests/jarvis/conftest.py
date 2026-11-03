"""Fixtures for the Jarvis smart-home tools: a fake Hue bridge, no network."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from openjarvis.tools import hue_bridge

GROUPS = {
    "1": {
        "type": "Room",
        "name": "Sleep",
        "lights": ["1", "2"],
        "state": {"any_on": False},
    },
    "4": {
        "type": "Room",
        "name": "Office",
        "lights": ["12"],
        "state": {"any_on": False},
    },
    "5": {
        "type": "Room",
        "name": "Hallway",
        "lights": ["14"],
        "state": {"any_on": True},
    },
    "10": {
        "type": "Room",
        "name": "Kitchen",
        "lights": ["16", "17"],
        "state": {"any_on": False},
    },
    "7": {
        "type": "Zone",
        "name": "Kitchen I",
        "lights": ["16"],
        "state": {"any_on": False},
    },
}
LIGHTS = {
    "1": {
        "name": "Bed 1 ct",
        "state": {"on": False, "reachable": True, "bri": 254, "ct": 366},
    },
    "2": {
        "name": "Bed 4 ct",
        "state": {"on": False, "reachable": False, "bri": 254, "ct": 366},
    },
    "12": {
        "name": "Hue Color Desk",
        "state": {
            "on": False,
            "reachable": True,
            "bri": 127,
            "xy": [0.3, 0.3],
            "ct": 300,
            "colormode": "xy",
        },
    },
    "14": {
        "name": "Hue filament",
        "state": {"on": True, "reachable": True, "bri": 200},
    },
    "16": {
        "name": "Kitchen white",
        "state": {"on": False, "reachable": True, "bri": 254},
    },
    "17": {
        "name": "Kitchen strip",
        "state": {
            "on": False,
            "reachable": True,
            "bri": 254,
            "xy": [0.4, 0.4],
            "colormode": "xy",
        },
    },
}


class FakeBridge:
    """Answers hue_bridge.request like a v1 bridge and applies PUTs to its own state."""

    def __init__(self) -> None:
        self.groups = copy.deepcopy(GROUPS)
        self.lights = copy.deepcopy(LIGHTS)
        self.puts: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, path: str, body: dict[str, Any] | None = None) -> Any:
        parts = path.strip("/").split("/")
        if body is not None:
            self.puts.append((path, body))
            if parts[0] == "groups":
                for lid in self.groups[parts[1]]["lights"]:
                    if self.lights[lid]["state"]["reachable"]:
                        self.lights[lid]["state"].update(body)
                self._refresh_any_on()
            else:
                self.lights[parts[1]]["state"].update(body)
            return [{"success": {"/%s/%s" % (path, k): v}} for k, v in body.items()]
        table = self.groups if parts[0] == "groups" else self.lights
        return copy.deepcopy(table[parts[1]] if len(parts) > 1 else table)

    def _refresh_any_on(self) -> None:
        for g in self.groups.values():
            g["state"]["any_on"] = any(
                self.lights[lid]["state"]["on"] for lid in g["lights"]
            )


@pytest.fixture
def bridge(monkeypatch: pytest.MonkeyPatch) -> FakeBridge:
    fake = FakeBridge()
    monkeypatch.setattr(hue_bridge, "request", fake)
    monkeypatch.setattr(hue_bridge.time, "sleep", lambda _s: None)
    monkeypatch.setattr(hue_bridge, "LOG_FILE", "/nonexistent-dir/hue-log.txt")
    return fake
