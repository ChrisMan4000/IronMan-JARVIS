"""Small scripts: benchmark grading and the wake-word counter."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
for folder in (TOOLS, TOOLS / "npu"):
    if str(folder) not in sys.path:
        sys.path.append(str(folder))

import bench  # noqa: E402
import wake_service  # noqa: E402


def test_tools_called_reads_the_tool_log():
    lines = [
        "12:00:01 hue_set {'room': 'Kitchen'}",
        "12:00:02 hue_set {...}",
        "12:00:03 rss_news",
        "",
        "x",
    ]
    assert bench.tools_called(lines) == ["hue_set", "rss_news"]


def test_grade():
    case = {"q": "Turn off the kitchen", "tool": "hue_set", "expect": "kitchen"}
    assert bench.grade(case, "The Kitchen is off.", ["hue_set"])["ok"]
    # Claimed without calling the tool:
    assert not bench.grade(case, "The Kitchen is off.", [])["ok"]
    chat = {"q": "Hello", "tool": "", "expect": ""}
    assert (
        bench.grade(chat, "Hi", [])["ok"]
        and not bench.grade(chat, "Hi", ["web_search"])["ok"]
    )


def test_summary():
    out = bench.summary([{"ok": True}, {"ok": False}, {"ok": True}], "gemma")
    assert (out["accuracy"], out["passed"], out["total"], out["model"]) == (
        66.7,
        2,
        3,
        "gemma",
    )


def test_wake_cooldown():
    assert wake_service.count_wake(0.9, now=10.0, last_wake=0.0)
    # Inside the cooldown:
    assert not wake_service.count_wake(0.9, now=10.0, last_wake=8.0)
    assert not wake_service.count_wake(0.2, now=10.0, last_wake=0.0)  # not sure enough


class FakeRequest:
    def __init__(self, host, origin=""):
        self.headers = {"Host": host, "Origin": origin}
        self.wfile = io.BytesIO()
        self.code, self.sent = None, {}

    def send_response(self, code):
        self.code = code

    def send_header(self, k, v):
        self.sent[k] = v

    def end_headers(self):
        pass


def test_counter_only_for_this_pc_and_the_hud():
    hud = FakeRequest("127.0.0.1:8766", "http://localhost:5173")
    wake_service.CounterHandler.do_GET(hud)
    assert hud.code == 200 and "wake_count" in json.loads(hud.wfile.getvalue())
    assert hud.sent["Access-Control-Allow-Origin"] == "http://localhost:5173"
    other_site = FakeRequest("127.0.0.1:8766", "https://evil.example")
    wake_service.CounterHandler.do_GET(other_site)
    assert "Access-Control-Allow-Origin" not in other_site.sent
    rebinding = FakeRequest("evil.example:8766")
    wake_service.CounterHandler.do_GET(rebinding)
    assert rebinding.code == 403
