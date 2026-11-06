"""Sonos tool: control one Sonos soundbar/speaker (made for the Arc Ultra) locally.

No account and no cloud: Sonos speakers accept UPnP/SOAP commands on port 1400 of the
home network. The speaker address comes from the user env var SONOS_IP (empty: the
tool does nothing). Only private addresses are accepted.
Actions: status, play, pause, next, previous, volume (0-100), volume_up, volume_down,
mute, unmute. Every change is read back and reported as "Verified: YES/NO".
apply() and read_state() are also meant for the local home-world helper.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

TOOL_NAME = "sonos_control"
VOLUME_CAP = 80  # a voice command never sets the volume above this
VOLUME_STEP = 10  # volume_up / volume_down change by this much
TIMEOUT = 4  # seconds for one request to the speaker
READ_BACK_DELAY = 0.6  # seconds before the speaker is read back
LOG_FILE = Path.home() / ".openjarvis" / "sonos-set-log.txt"
ACTIONS = (
    "status", "play", "pause", "next", "previous",
    "volume", "volume_up", "volume_down", "mute", "unmute",
)  # fmt: skip
PLAYING = ("PLAYING", "TRANSITIONING")
STOPPED = ("PAUSED_PLAYBACK", "STOPPED")

_AVT = (
    "/MediaRenderer/AVTransport/Control",
    "urn:schemas-upnp-org:service:AVTransport:1",
)
_RC = (
    "/MediaRenderer/RenderingControl/Control",
    "urn:schemas-upnp-org:service:RenderingControl:1",
)
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class SonosError(Exception):
    """A short, readable problem (shown to the user as the tool reply)."""


def speaker_ip() -> str:
    """The speaker address from SONOS_IP; must be a private network address."""
    ip = os.environ.get("SONOS_IP", "").strip()
    if not ip:
        raise SonosError("SONOS_IP is not set (user environment variable).")
    try:
        private = ipaddress.ip_address(ip).is_private
    except ValueError:
        private = False
    if not private:
        raise SonosError("SONOS_IP must be a private network address.")
    return ip


def _soap(service: tuple[str, str], action: str, args: str = "") -> str:
    """Send one UPnP action; return the reply text. Raises SonosError."""
    path, urn = service
    body = (
        '<?xml version="1.0"?><s:Envelope'
        ' xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        '<u:%s xmlns:u="%s"><InstanceID>0</InstanceID>%s</u:%s></s:Body></s:Envelope>'
    ) % (action, urn, args, action)
    req = urllib.request.Request(
        "http://%s:1400%s" % (speaker_ip(), path),
        data=body.encode("utf-8"),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": '"%s#%s"' % (urn, action),
        },
    )
    try:
        with _NO_PROXY.open(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        code = re.search(r"<errorCode>(\d+)</errorCode>", text)
        raise SonosError(
            "The speaker refused %s (UPnP error %s). It may not allow this with"
            " the current source (for example next/previous on TV sound)."
            % (action, code.group(1) if code else e.code)
        ) from None
    except (urllib.error.URLError, OSError):
        raise SonosError("Cannot reach the speaker (off, asleep or wrong IP?).") from None


def _tag(text: str, name: str) -> str:
    m = re.search(r"<%s>([^<]*)</%s>" % (name, name), text)
    return m.group(1) if m else ""


def read_state() -> dict[str, Any]:
    """Transport state, volume (0-100), mute and a rough source of the speaker."""
    transport = _soap(_AVT, "GetTransportInfo")
    volume = _soap(_RC, "GetVolume", "<Channel>Master</Channel>")
    mute = _soap(_RC, "GetMute", "<Channel>Master</Channel>")
    media = _soap(_AVT, "GetMediaInfo")
    uri = _tag(media, "CurrentURI")
    return {
        "state": _tag(transport, "CurrentTransportState") or "UNKNOWN",
        "volume": int(_tag(volume, "CurrentVolume") or 0),
        "muted": _tag(mute, "CurrentMute") == "1",
        "source": "TV" if uri.startswith("x-sonos-htastream") else "stream/other",
    }


def _describe(st: dict[str, Any]) -> str:
    return "%s, volume %d%%%s, source %s" % (
        st["state"],
        st["volume"],
        " (muted)" if st["muted"] else "",
        st["source"],
    )


def _set_volume(level: int) -> None:
    _soap(_RC, "SetVolume", "<Channel>Master</Channel><DesiredVolume>%d</DesiredVolume>" % level)


def apply(action: str, value: Any = None) -> tuple[str, bool]:
    """Do one action, read the speaker back, return (text, ok). Raises SonosError."""
    action = str(action or "status").strip().lower()
    if action not in ACTIONS:
        raise SonosError("Unknown action. Use: %s." % ", ".join(ACTIONS))
    before = read_state()
    if action == "status":
        return "Sonos: " + _describe(before), True
    note, want_vol = "", None
    if action == "play":
        _soap(_AVT, "Play", "<Speed>1</Speed>")
    elif action == "pause":
        _soap(_AVT, "Pause")
    elif action == "next":
        _soap(_AVT, "Next")
    elif action == "previous":
        _soap(_AVT, "Previous")
    elif action in ("mute", "unmute"):
        flag = 1 if action == "mute" else 0
        _soap(_RC, "SetMute", "<Channel>Master</Channel><DesiredMute>%d</DesiredMute>" % flag)
    else:  # volume, volume_up, volume_down
        if action == "volume":
            try:
                target = int(float(value))
            except (TypeError, ValueError):
                raise SonosError("volume needs a number 0-100.") from None
        else:
            sign = 1 if action == "volume_up" else -1
            target = before["volume"] + sign * VOLUME_STEP
        want_vol = max(0, min(VOLUME_CAP, target))
        if want_vol != target and target > VOLUME_CAP:
            note = " (limited to the cap of %d%%)" % VOLUME_CAP
        _set_volume(want_vol)
    time.sleep(READ_BACK_DELAY)
    now = read_state()
    ok = True
    if action == "play":
        ok = now["state"] in PLAYING
    elif action == "pause":
        ok = now["state"] in STOPPED
    elif action in ("mute", "unmute"):
        ok = now["muted"] == (action == "mute")
    elif want_vol is not None:
        ok = now["volume"] == want_vol
    text = "Sent %s%s. Now: %s. Verified: %s." % (
        action,
        note,
        _describe(now),
        "YES" if ok else "NO",
    )
    if action in ("next", "previous"):
        text = "Sent %s. Now: %s. (No read-back possible for track skips.)" % (
            action,
            _describe(now),
        )
    return text, ok


def _log(params: dict[str, Any]) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.now().isoformat(timespec="seconds"), json.dumps(params)))
    except OSError:
        pass  # logging must never break the tool


@ToolRegistry.register(TOOL_NAME)
class SonosControlTool(BaseTool):
    tool_id = TOOL_NAME

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
            description=(
                "ALWAYS call this tool when the user asks to play, pause, skip to"
                " the next or previous track, change or set the volume, mute or"
                " unmute the Sonos / sound bar / Arc / TV speaker, or asks what is"
                " playing or how loud it is. Actions: status, play, pause, next,"
                " previous, volume (needs value 0-100), volume_up, volume_down,"
                " mute, unmute. Never say the sound bar was changed unless this"
                " tool returned a result; report only what it returned."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "one of: " + ", ".join(ACTIONS)},
                    "value": {"type": "integer", "description": "volume 0-100 (only for action volume)"},
                },
                "required": ["action"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        _log({k: params.get(k) for k in ("action", "value")})
        try:
            text, ok = apply(params.get("action", "status"), params.get("value"))
            return ToolResult(tool_name=TOOL_NAME, content=text, success=ok)
        except SonosError as e:
            return ToolResult(tool_name=TOOL_NAME, content="Sonos error: %s" % e, success=False)
        except Exception as e:  # any other problem becomes a short tool reply
            return ToolResult(tool_name=TOOL_NAME, content="Sonos error: %s" % type(e).__name__, success=False)
