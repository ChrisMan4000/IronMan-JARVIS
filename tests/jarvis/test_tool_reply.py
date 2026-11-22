"""The shared reply builder of the home-control tools."""

from __future__ import annotations

from openjarvis.tools import tool_reply


def test_reply_carries_name_text_and_flag():
    r = tool_reply.reply("demo", "all good")
    assert (r.tool_name, r.content, r.success) == ("demo", "all good", True)
    assert tool_reply.reply("demo", "nope", ok=False).success is False


def test_failure_for_marks_failures():
    fail = tool_reply.failure_for("demo")
    r = fail("state must be on or off.")
    assert (r.tool_name, r.content, r.success) == ("demo", "state must be on or off.", False)


def test_reply_for_defaults_to_success():
    result = tool_reply.reply_for("demo")
    assert result("fine").success is True
    assert result("broken", False).success is False
