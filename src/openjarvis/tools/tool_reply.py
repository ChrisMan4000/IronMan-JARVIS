# New file for the IronMan J.A.R.V.I.S. project (see NOTICE).
"""One place that builds the short text replies of the home-control tools.

Every tool (Hue, Oxxify, Tado, Sonos, RSS, document search) answers with a
ToolResult carrying its own name, the text and a success flag. This module makes
that reply in one way, so the tools do not each carry their own copy.

    _fail = tool_reply.failure_for(TOOL_NAME)
    return _fail("state must be on or off.")
"""

from __future__ import annotations

from collections.abc import Callable

from openjarvis.core.types import ToolResult


def reply(tool_name: str, text: str, ok: bool = True) -> ToolResult:
    """A tool reply with the given text; ok=False marks it as a failure."""
    return ToolResult(tool_name=tool_name, content=text, success=ok)


def failure_for(tool_name: str) -> Callable[[str], ToolResult]:
    """A function fail(text) that answers as a failed call of this tool."""

    def fail(text: str) -> ToolResult:
        return reply(tool_name, text, ok=False)

    return fail


def reply_for(tool_name: str) -> Callable[..., ToolResult]:
    """A function result(text, ok=True) that answers as this tool."""

    def result(text: str, ok: bool = True) -> ToolResult:
        return reply(tool_name, text, ok)

    return result
