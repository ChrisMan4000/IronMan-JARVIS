"""Shared Philips Hue bridge client for the hue_* tools and the local helper.

One place for the bridge address, the app key file, the HTTP calls, room matching
and the call log, so every Hue tool finds the bridge the same way and fails with
the same clear message.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from typing import Any

from openjarvis.tools import device_log

logger = logging.getLogger(__name__)

_JARVIS_DIR = os.path.join(os.path.expanduser("~"), ".openjarvis")
KEY_FILE = os.path.join(_JARVIS_DIR, "hue-key.txt")  # app key: never print or share it
LOG_FILE = os.path.join(_JARVIS_DIR, "hue-set-log.txt")
TIMEOUT = 5  # seconds per bridge request
ROOM_FILLER = ("the", "light", "lights", "lamp", "lamps", "room")
_HOST_RE = re.compile(r"[A-Za-z0-9.\-]+(:\d{1,5})?")


class HueBridgeError(RuntimeError):
    """The bridge is not configured or answered with an error entry."""


def bridge_address() -> str:
    """Bridge IP from HUE_BRIDGE_IP (read on each call), else the Windows settings.

    The fallback matters when the helper was started before the variable was set.
    """
    addr = os.environ.get("HUE_BRIDGE_IP", "").strip()
    if addr:
        return addr
    try:
        import winreg
    except ImportError:  # not Windows
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, "HUE_BRIDGE_IP")[0]).strip()
    except OSError:  # variable not set in the user settings either
        return ""


def _app_key() -> str:
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def _raise_on_bridge_error(reply: Any) -> None:
    """The bridge answers HTTP 200 with [{"error": {...}}] when it refuses something."""
    if not isinstance(reply, list):
        return
    errors = [
        item["error"] for item in reply if isinstance(item, dict) and "error" in item
    ]
    if errors:
        raise HueBridgeError(str(errors[0].get("description", "bridge error")))


def request(path: str, body: dict[str, Any] | None = None) -> Any:
    """GET ``/api/<key><path>`` (no body) or PUT the JSON body; return the reply.

    Raises HueBridgeError when no valid bridge address is set or the bridge reports an
    error; OSError (missing key file, network trouble) passes through unchanged.
    """
    addr = bridge_address()
    if not addr:
        raise HueBridgeError("no bridge address (set HUE_BRIDGE_IP)")
    if not _HOST_RE.fullmatch(addr):
        raise HueBridgeError("HUE_BRIDGE_IP is not a plain host name or IP address")
    req = urllib.request.Request(
        "http://%s/api/%s%s" % (addr, _app_key(), path),
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method="GET" if body is None else "PUT",
        headers={"Content-Type": "application/json"},
    )
    # The URL is always http:// plus a validated host: no file:// or custom scheme.
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # nosec B310
        reply = json.loads(r.read().decode("utf-8"))
    _raise_on_bridge_error(reply)
    return reply


def error_text(exc: BaseException) -> str:
    """Short, safe text for a tool reply: the bridge's reason, else the error type."""
    return str(exc) if isinstance(exc, HueBridgeError) else type(exc).__name__


def log_call(tool: str, params: dict[str, Any]) -> None:
    """One shortened line per call in hue-set-log.txt (what was asked)."""
    device_log.append_change(LOG_FILE, "%s %s" % (tool, repr(params)[:300]))


def rooms(groups: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """(group id, name) of every Hue Room; zones and entertainment groups skipped."""
    return [
        (gid, str(g.get("name", "")))
        for gid, g in groups.items()
        if g.get("type") == "Room"
    ]


def find_room(groups: dict[str, dict[str, Any]], text: str) -> tuple[str, str] | None:
    """Match a spoken room name to (group id, name); None when nothing or several fit.

    Order: exact name; exact without a plural "s"; a unique partial name; the phrase
    without filler words (the, light(s), lamp(s), room) equal to a room name. The
    last rule is strict on purpose: a looser one once switched the wrong room.
    """
    want = text.strip().lower()
    if not want:
        return None
    singular = want[:-1] if len(want) > 3 and want.endswith("s") else want
    candidates = rooms(groups)
    for wanted in (want, singular):
        for gid, name in candidates:
            if name.lower() == wanted:
                return gid, name
    partial = [(gid, name) for gid, name in candidates if singular in name.lower()]
    if len(partial) == 1:
        return partial[0]
    cleaned = " ".join(w for w in singular.split() if w not in ROOM_FILLER)
    loose = [
        (gid, name)
        for gid, name in candidates
        if cleaned and name.lower() in (cleaned, cleaned[:-1])
    ]
    return loose[0] if len(loose) == 1 else None


def set_room_power(group_id: str, on: bool) -> Any:
    """Switch every light of a room on or off; returns the bridge reply."""
    return request("/groups/%s/action" % group_id, {"on": on})


def room_any_on(group_id: str) -> bool:
    """Read a room back: True when at least one of its lights reports on."""
    return bool(request("/groups/%s" % group_id).get("state", {}).get("any_on"))


READ_BACK_DELAY = 1.0  # seconds the bridge needs before a room reads back its new state


def read_back_report(
    group_id: str, room: str, want_on: bool, reply: Any
) -> tuple[str, bool]:
    """Wait, read the room back and describe it; ok is True only when it matches.

    A room whose lights are all unreachable can still read back as matching, because the
    bridge echoes the request; hue_all_set checks every light for that case.
    """
    time.sleep(READ_BACK_DELAY)
    any_on = room_any_on(group_id)
    ok = any_on == want_on
    text = (
        "Sent: %s %s. Bridge reply: %s. Verified by reading back: %s"
        " (any light on now: %s)."
        % (
            room,
            "on" if want_on else "off",
            json.dumps(reply),
            "YES" if ok else "NO (some lights in this room may be unreachable)",
            any_on,
        )
    )
    return text, ok
