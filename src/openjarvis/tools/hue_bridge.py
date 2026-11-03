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

try:  # Windows only: the user's saved environment variables
    import winreg
except ImportError:
    winreg = None

from openjarvis.tools import device_log

logger = logging.getLogger(__name__)

_JARVIS_DIR = os.path.join(os.path.expanduser("~"), ".openjarvis")
KEY_FILE = os.path.join(_JARVIS_DIR, "hue-key.txt")  # app key: never print or share it
LOG_FILE = os.path.join(_JARVIS_DIR, "hue-set-log.txt")
TIMEOUT = 5  # seconds per bridge request
ROOM_FILLER = ("the", "light", "lights", "lamp", "lamps", "room")
BRIDGE_API_URL = "http://{host}/api/{key}{path}"  # the bridge's local v1 API
_HOST_RE = re.compile(r"[A-Za-z0-9.\-]+(:\d{1,5})?")


class HueBridgeError(RuntimeError):
    """The bridge is not configured or answered with an error entry."""


class UnknownRoom(HueBridgeError):
    """No room (or more than one) matches; the message lists the rooms."""


def bridge_address() -> str:
    """Bridge IP from HUE_BRIDGE_IP (read on each call), else the Windows settings.

    The fallback matters when the helper was started before the variable was set.
    """
    addr = os.environ.get("HUE_BRIDGE_IP", "").strip()
    if addr:
        return addr
    if winreg is None:  # not Windows
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
        BRIDGE_API_URL.format(host=addr, key=_app_key(), path=path),
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


def lookup_room(text: str) -> tuple[str, str]:
    """(group id, room name) for a spoken room; UnknownRoom lists rooms if none fits."""
    groups = request("/groups")
    match = find_room(groups, text)
    if match is None:
        raise UnknownRoom(
            "No such room. Rooms: %s" % ", ".join(n for _g, n in rooms(groups))
        )
    return match


def power_state(text: object) -> bool | None:
    """True for "on", False for "off", None for anything else."""
    state = str(text or "").strip().lower()
    return {"on": True, "off": False}.get(state)


def set_room_power(group_id: str, on: bool) -> Any:
    """Switch every light of a room on or off; returns the bridge reply."""
    return request("/groups/%s/action" % group_id, {"on": on})


# Read-back verdicts for one room, from the most to the least certain.
VERIFIED, PARTLY, UNCONFIRMABLE, FAILED = (
    "verified",
    "partly",
    "unconfirmable",
    "failed",
)


def room_verdict(
    name: str,
    light_ids: list[str],
    lights: dict[str, dict[str, Any]],
    sent: bool,
    want_on: bool,
) -> tuple[str, str]:
    """(verdict, report line) for one room after the switch command."""
    state = "on" if want_on else "off"
    if not sent:
        return FAILED, "%s: FAILED, the bridge did not accept the command" % name
    reachable, unreachable = [], []
    for lid in light_ids:
        light = lights.get(lid)
        if light is not None and light.get("state", {}).get("reachable", True):
            reachable.append(light)
        else:  # unreachable, or missing from the bridge's light list
            unreachable.append(light.get("name", lid) if light else lid)
    if not reachable:
        return UNCONFIRMABLE, "%s: NOT CONFIRMABLE, all lights unreachable (%s)" % (
            name,
            ", ".join(unreachable),
        )
    if not all(
        bool(light.get("state", {}).get("on")) == want_on for light in reachable
    ):
        return FAILED, "%s: MISMATCH, a reachable light is not %s" % (name, state)
    if unreachable:
        return PARTLY, "%s: confirmed %s for the reachable lights; unreachable: %s" % (
            name,
            state,
            ", ".join(unreachable),
        )
    return VERIFIED, "%s: verified %s" % (name, state)


def room_lights(group_id: str) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """A room's light ids and the bridge's current record of every light."""
    ids = [str(x) for x in request("/groups/%s" % group_id).get("lights", [])]
    return ids, request("/lights")


ROOM_READ_BACK_DELAY = 1.0  # seconds before the lights report their new state


def read_back_report(
    group_id: str, room: str, want_on: bool, reply: Any
) -> tuple[str, bool]:
    """Wait, read the room's lights back one by one and describe them.

    ok is True when every reachable light matches (room_verdict VERIFIED or PARTLY).
    The room's own any_on is not used: the bridge echoes the request there even when
    all its lights are unreachable.
    """
    time.sleep(ROOM_READ_BACK_DELAY)
    ids, lights = room_lights(group_id)
    verdict, line = room_verdict(room, ids, lights, True, want_on)
    text = "Sent: %s %s. Bridge reply: %s. Read back light by light: %s." % (
        room,
        "on" if want_on else "off",
        json.dumps(reply),
        line,
    )
    return text, verdict in (VERIFIED, PARTLY)
