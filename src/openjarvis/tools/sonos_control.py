"""Sonos tool: control one Sonos soundbar/speaker (made for the Arc Ultra) locally.

No account and no cloud: Sonos speakers accept UPnP/SOAP commands on port 1400 of the
home network. The speaker address comes from the user env var SONOS_IP (empty: the
tool does nothing). Only private addresses are accepted.
Actions: status, play, pause, next, previous, volume (0-100), volume_up, volume_down,
mute, unmute, favorites (list the Sonos favorites), play_favorite (start one by name)
and tv (switch to TV sound). Every change is read back and reported as "Verified: YES/NO".
apply() and read_state() are also meant for the local home-world helper.
"""

from __future__ import annotations

import difflib
import html
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
from xml.sax.saxutils import escape

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
    "favorites", "play_favorite", "tv",
)  # fmt: skip
PLAYING = ("PLAYING", "TRANSITIONING")
STOPPED = ("PAUSED_PLAYBACK", "STOPPED")
LONG_TIMEOUT = 15  # starting a stream can take the speaker several seconds
PLAY_FAV_DELAY = 1.5  # seconds before a started favorite is read back (radio is slow)
# favorites with these addresses are played through the speaker queue
QUEUE_SCHEMES = ("x-rincon-cpcontainer", "x-rincon-playlist", "file:")

_AVT = (
    "/MediaRenderer/AVTransport/Control",
    "urn:schemas-upnp-org:service:AVTransport:1",
)
_RC = (
    "/MediaRenderer/RenderingControl/Control",
    "urn:schemas-upnp-org:service:RenderingControl:1",
)
_CD = (
    "/MediaServer/ContentDirectory/Control",
    "urn:schemas-upnp-org:service:ContentDirectory:1",
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


def _soap(
    service: tuple[str, str],
    action: str,
    args: str = "",
    instance: bool = True,
    timeout: float | None = None,
) -> str:
    """Send one UPnP action; return the reply text. Raises SonosError."""
    path, urn = service
    body = (
        '<?xml version="1.0"?><s:Envelope'
        ' xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        '<u:%s xmlns:u="%s">%s%s</u:%s></s:Body></s:Envelope>'
    ) % (action, urn, "<InstanceID>0</InstanceID>" if instance else "", args, action)
    req = urllib.request.Request(
        "http://%s:1400%s" % (speaker_ip(), path),
        data=body.encode("utf-8"),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": '"%s#%s"' % (urn, action),
        },
    )
    try:
        with _NO_PROXY.open(req, timeout=timeout or TIMEOUT) as resp:
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


def _udn() -> str:
    """The speaker's RINCON id (needed for the queue and TV input addresses)."""
    try:
        with _NO_PROXY.open(
            "http://%s:1400/xml/device_description.xml" % speaker_ip(), timeout=TIMEOUT
        ) as resp:
            text = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        raise SonosError("Cannot reach the speaker (off, asleep or wrong IP?).") from None
    m = re.search(r"<UDN>uuid:(RINCON_[0-9A-Fa-f]+)</UDN>", text)
    if not m:
        raise SonosError("The speaker did not report its id.")
    return m.group(1)


def list_favorites() -> list[dict[str, Any]]:
    """The Sonos favorites: title, service, art (http only), playable, uri, meta."""
    reply = _soap(
        _CD,
        "Browse",
        "<ObjectID>FV:2</ObjectID><BrowseFlag>BrowseDirectChildren</BrowseFlag>"
        "<Filter>*</Filter><StartingIndex>0</StartingIndex><RequestedCount>100</RequestedCount>"
        "<SortCriteria></SortCriteria>",
        instance=False,
    )
    found = re.search(r"<Result>(.*?)</Result>", reply, re.S)
    didl = html.unescape(found.group(1)) if found else ""
    out: list[dict[str, Any]] = []
    for item in re.findall(r"<item\b.*?</item>", didl, re.S):
        res = re.search(r"<res[^>]*>(.*?)</res>", item, re.S)
        uri = html.unescape(res.group(1)).strip() if res else ""
        art = html.unescape(_tag(item, "upnp:albumArtURI")).strip()
        out.append(
            {
                "title": html.unescape(_tag(item, "dc:title")).strip(),
                "service": html.unescape(_tag(item, "r:description")).strip(),
                "art": art if art.startswith(("http://", "https://")) else "",
                "uri": uri,
                "meta": html.unescape(_tag(item, "r:resMD")),
                "playable": bool(uri),
            }
        )
    return [f for f in out if f["title"]]


def _find_favorite(name: str, favs: list[dict[str, Any]]) -> dict[str, Any]:
    want = name.strip().lower()
    if not want:
        raise SonosError("play_favorite needs the name of a favorite (see action favorites).")
    exact = [f for f in favs if f["title"].lower() == want]
    if len(exact) == 1:
        return exact[0]
    part = [f for f in favs if want in f["title"].lower()]
    if len(part) == 1:
        return part[0]
    if len(part) > 1:
        raise SonosError(
            "More than one favorite matches '%s': %s."
            % (name, ", ".join(f["title"] for f in part))
        )
    by_service = [f for f in favs if f["service"].lower() == want and f["playable"]]
    if len(by_service) == 1:
        return by_service[0]
    titles = [f["title"].lower() for f in favs]
    close = difflib.get_close_matches(want, titles, n=1, cutoff=0.6)
    if close:
        return favs[titles.index(close[0])]
    raise SonosError(
        "No favorite named '%s'. Favorites: %s."
        % (name, ", ".join(f["title"] for f in favs) or "none")
    )


def play_favorite(name: str) -> dict[str, Any]:
    """Start one favorite by (fuzzy) name; return it. Raises SonosError."""
    fav = _find_favorite(name, list_favorites())
    if not fav["playable"]:
        raise SonosError("'%s' is a folder; open it in the Sonos app." % fav["title"])
    uri, meta = fav["uri"], fav["meta"]
    if uri.startswith(QUEUE_SCHEMES):  # playlists/albums: replace the queue, play from it
        _soap(_AVT, "RemoveAllTracksFromQueue")
        _soap(
            _AVT,
            "AddURIToQueue",
            "<EnqueuedURI>%s</EnqueuedURI><EnqueuedURIMetaData>%s</EnqueuedURIMetaData>"
            "<DesiredFirstTrackNumberEnqueued>0</DesiredFirstTrackNumberEnqueued>"
            "<EnqueueAsNext>1</EnqueueAsNext>" % (escape(uri), escape(meta)),
            timeout=LONG_TIMEOUT,
        )
        _soap(
            _AVT,
            "SetAVTransportURI",
            "<CurrentURI>x-rincon-queue:%s#0</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>"
            % _udn(),
            timeout=LONG_TIMEOUT,
        )
    else:  # radio streams and the like
        _soap(
            _AVT,
            "SetAVTransportURI",
            "<CurrentURI>%s</CurrentURI><CurrentURIMetaData>%s</CurrentURIMetaData>"
            % (escape(uri), escape(meta)),
            timeout=LONG_TIMEOUT,
        )
    _soap(_AVT, "Play", "<Speed>1</Speed>", timeout=LONG_TIMEOUT)
    return fav


def _junk_title(title: str) -> bool:
    return (
        not title
        or len(title) > 80
        or "?" in title
        or title.startswith("x-")
        or title == "NOT_IMPLEMENTED"
    )


def now_playing() -> str:
    """Title and artist of the current track, or empty (TV sound has none)."""
    try:
        info = _soap(_AVT, "GetPositionInfo")
    except SonosError:
        return ""
    meta = html.unescape(_tag(info, "TrackMetaData"))
    title = html.unescape(_tag(meta, "dc:title")).strip()
    artist = html.unescape(_tag(meta, "dc:creator")).strip()
    if _junk_title(title):  # radio ads and streams: use the station name instead
        try:
            media = _soap(_AVT, "GetMediaInfo")
        except SonosError:
            return ""
        station = html.unescape(_tag(html.unescape(_tag(media, "CurrentURIMetaData")), "dc:title"))
        return "" if _junk_title(station.strip()) else station.strip()
    return "%s - %s" % (title, artist) if artist else title


def _favorites_text() -> str:
    favs = list_favorites()
    if not favs:
        return "No Sonos favorites found. Add some in the Sonos app (My Sonos > Favorites)."
    ok = [
        "%s (%s)" % (f["title"], f["service"]) if f["service"] else f["title"]
        for f in favs
        if f["playable"]
    ]
    app = [f["title"] for f in favs if not f["playable"]]
    text = "Favorites you can start: %s." % ("; ".join(ok) or "none")
    if app:
        text += " Only in the Sonos app: %s." % ", ".join(app)
    return text


def _play_favorite_text(name: Any) -> tuple[str, bool]:
    fav = play_favorite(str(name or ""))
    time.sleep(PLAY_FAV_DELAY)
    now = read_state()
    ok = now["state"] in PLAYING
    where = " (%s)" % fav["service"] if fav["service"] else ""
    text = "Started favorite '%s'%s. Now: %s. Verified: %s." % (
        fav["title"],
        where,
        _describe(now),
        "YES" if ok else "NO",
    )
    return text, ok


def _tv_text() -> tuple[str, bool]:
    _soap(
        _AVT,
        "SetAVTransportURI",
        "<CurrentURI>x-sonos-htastream:%s:spdif</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>"
        % _udn(),
    )
    time.sleep(READ_BACK_DELAY)
    now = read_state()
    ok = now["source"] == "TV"
    text = "Switched to TV sound. Now: %s. Verified: %s. (You hear something only while the TV sends sound.)" % (
        _describe(now),
        "YES" if ok else "NO",
    )
    return text, ok


def apply(action: str, value: Any = None) -> tuple[str, bool]:
    """Do one action, read the speaker back, return (text, ok). Raises SonosError."""
    action = str(action or "status").strip().lower()
    if action not in ACTIONS:
        raise SonosError("Unknown action. Use: %s." % ", ".join(ACTIONS))
    if action == "favorites":
        return _favorites_text(), True
    if action == "play_favorite":
        return _play_favorite_text(value)
    if action == "tv":
        return _tv_text()
    before = read_state()
    if action == "status":
        playing = now_playing() if before["state"] in PLAYING else ""
        extra = ". Playing: %s" % playing if playing else ""
        return "Sonos: " + _describe(before) + extra, True
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
                " unmute the Sonos / sound bar / Arc / TV speaker, asks what is"
                " playing or how loud it is, asks which favorites exist, wants a"
                " favorite (radio station, playlist, Spotify or SoundCloud saved in"
                " Sonos) started, or wants the TV sound. Actions: status, play,"
                " pause, next, previous, volume (needs value 0-100), volume_up,"
                " volume_down, mute, unmute, favorites (list the names),"
                " play_favorite (needs name, for example FluxFM), tv (switch to TV"
                " sound). Never say the sound bar was changed unless this tool"
                " returned a result; report only what it returned."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "one of: " + ", ".join(ACTIONS)},
                    "value": {"type": "integer", "description": "volume 0-100 (only for action volume)"},
                    "name": {"type": "string", "description": "favorite name (only for action play_favorite)"},
                },
                "required": ["action"],
            },
            category="smart-home",
        )

    def execute(self, **params: Any) -> ToolResult:
        _log({k: params.get(k) for k in ("action", "value", "name")})
        try:
            action = params.get("action", "status")
            is_fav = str(action).strip().lower() == "play_favorite"
            arg = params.get("name") if is_fav and params.get("name") else params.get("value")
            text, ok = apply(action, arg)
            return ToolResult(tool_name=TOOL_NAME, content=text, success=ok)
        except SonosError as e:
            return ToolResult(tool_name=TOOL_NAME, content="Sonos error: %s" % e, success=False)
        except Exception as e:  # any other problem becomes a short tool reply
            return ToolResult(tool_name=TOOL_NAME, content="Sonos error: %s" % type(e).__name__, success=False)
