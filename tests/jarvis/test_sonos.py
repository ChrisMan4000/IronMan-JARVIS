"""Tests for the Sonos tool. No speaker is needed: the SOAP call is replaced by a fake."""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

import pytest

from openjarvis.tools import sonos_control as sc


class FakeSpeaker:
    """Answers the few UPnP actions the tool uses and remembers what it was told."""

    def __init__(self) -> None:
        self.volume = 17
        self.muted = False
        self.state = "STOPPED"
        self.calls: list[str] = []
        self.sent: list[tuple[str, str]] = []  # (action, args)
        self.uri = "x-sonos-htastream:RINCON_1:spdif"
        self.favorites = ""

    def soap(
        self, service: tuple[str, str], action: str, args: str = "", instance: bool = True,
        timeout: float | None = None,
    ) -> str:
        self.calls.append(action)
        self.sent.append((action, args))
        if action == "GetTransportInfo":
            return "<CurrentTransportState>%s</CurrentTransportState>" % self.state
        if action == "GetVolume":
            return "<CurrentVolume>%d</CurrentVolume>" % self.volume
        if action == "GetMute":
            return "<CurrentMute>%d</CurrentMute>" % int(self.muted)
        if action == "GetMediaInfo":
            return "<CurrentURI>%s</CurrentURI>" % self.uri
        if action == "Browse":
            return self.favorites
        if action == "SetAVTransportURI":
            self.uri = re.search(r"<CurrentURI>(.*?)</CurrentURI>", args).group(1)
        if action == "SetVolume":
            self.volume = int(re.search(r"<DesiredVolume>(\d+)<", args).group(1))
        elif action == "SetMute":
            self.muted = "<DesiredMute>1<" in args
        elif action == "Play":
            self.state = "PLAYING"
        elif action == "Pause":
            self.state = "PAUSED_PLAYBACK"
        return ""


@pytest.fixture
def speaker(monkeypatch: pytest.MonkeyPatch, tmp_path) -> FakeSpeaker:
    fake = FakeSpeaker()
    monkeypatch.setattr(sc, "_soap", fake.soap)
    monkeypatch.setattr(sc, "READ_BACK_DELAY", 0)
    monkeypatch.setattr(sc, "PLAY_FAV_DELAY", 0)
    monkeypatch.setattr(sc, "_udn", lambda: "RINCON_TEST")
    monkeypatch.setattr(sc, "LOG_FILE", tmp_path / "sonos-set-log.txt")
    monkeypatch.setenv("SONOS_IP", "192.168.1.50")
    return fake


def test_status_reads_state(speaker: FakeSpeaker) -> None:
    text, ok = sc.apply("status")
    assert ok
    assert "STOPPED" in text and "17%" in text and "TV" in text
    assert speaker.calls.count("SetVolume") == 0


def test_volume_is_set_and_verified(speaker: FakeSpeaker) -> None:
    text, ok = sc.apply("volume", 30)
    assert ok and speaker.volume == 30
    assert "Verified: YES" in text


def test_volume_is_capped(speaker: FakeSpeaker) -> None:
    text, ok = sc.apply("volume", 100)
    assert ok and speaker.volume == sc.VOLUME_CAP
    assert "cap" in text


def test_volume_up_and_down_use_the_step(speaker: FakeSpeaker) -> None:
    sc.apply("volume_up")
    assert speaker.volume == 17 + sc.VOLUME_STEP
    sc.apply("volume_down")
    assert speaker.volume == 17
    sc.apply("volume", 5)
    sc.apply("volume_down")
    assert speaker.volume == 0  # never below zero


def test_mute_and_unmute(speaker: FakeSpeaker) -> None:
    assert sc.apply("mute")[1] and speaker.muted
    assert sc.apply("unmute")[1] and not speaker.muted


def test_play_and_pause_are_read_back(speaker: FakeSpeaker) -> None:
    assert sc.apply("play")[1] and speaker.state == "PLAYING"
    assert sc.apply("pause")[1] and speaker.state == "PAUSED_PLAYBACK"


def test_unknown_action_and_bad_volume(speaker: FakeSpeaker) -> None:
    with pytest.raises(sc.SonosError):
        sc.apply("dance")
    with pytest.raises(sc.SonosError):
        sc.apply("volume", "loud")


def test_speaker_ip_must_be_set_and_private(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SONOS_IP", raising=False)
    with pytest.raises(sc.SonosError):
        sc.speaker_ip()
    monkeypatch.setenv("SONOS_IP", "8.8.8.8")
    with pytest.raises(sc.SonosError):
        sc.speaker_ip()
    monkeypatch.setenv("SONOS_IP", "not an ip")
    with pytest.raises(sc.SonosError):
        sc.speaker_ip()
    monkeypatch.setenv("SONOS_IP", "10.0.0.7")
    assert sc.speaker_ip() == "10.0.0.7"


def test_tool_reply_and_log(speaker: FakeSpeaker, tmp_path) -> None:
    res = sc.SonosControlTool().execute(action="volume", value=25)
    assert res.success and "Verified: YES" in res.content
    assert '"volume"' in (tmp_path / "sonos-set-log.txt").read_text(encoding="utf-8")


def test_tool_reports_errors_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SONOS_IP", raising=False)
    res = sc.SonosControlTool().execute(action="status")
    assert not res.success and "SONOS_IP" in res.content


RADIO = ("FluxFM", "Sonos Radio", "x-sonosapi-stream:s1?sid=303&flags=8224", "https://art.example/flux.png")
LIST = ("My Shazam Tracks", "Spotify", "x-rincon-cpcontainer:1006206cspotify%3aplaylist%3a1", "https://art.example/s.jpg")
RADIO2 = ("ORF Radio FM4", "Sonos Radio", "x-sonosapi-stream:s2?sid=303", "https://art.example/fm4.png")
FOLDER = ("Trending Now", "Sonos Radio", "", "")


def _meta(title: str) -> str:
    return "<DIDL-Lite><item><dc:title>%s</dc:title></item></DIDL-Lite>" % title


def _browse_reply(items) -> str:
    parts = []
    for title, service, uri, art in items:
        res = '<res protocolInfo="x">%s</res>' % escape(uri) if uri else ""
        parts.append(
            '<item id="FV:2/1" parentID="FV:2"><dc:title>%s</dc:title>%s'
            "<upnp:albumArtURI>%s</upnp:albumArtURI><r:description>%s</r:description>"
            "<r:resMD>%s</r:resMD></item>"
            % (escape(title), res, escape(art), escape(service), escape(_meta(title)))
        )
    didl = "<DIDL-Lite>%s</DIDL-Lite>" % "".join(parts)
    return "<Result>%s</Result><TotalMatches>%d</TotalMatches>" % (escape(didl), len(items))


@pytest.fixture
def favs(speaker: FakeSpeaker) -> FakeSpeaker:
    speaker.favorites = _browse_reply([RADIO, LIST, RADIO2, FOLDER])
    return speaker


def test_favorites_are_listed(favs: FakeSpeaker) -> None:
    items = sc.list_favorites()
    assert [f["title"] for f in items] == ["FluxFM", "My Shazam Tracks", "ORF Radio FM4", "Trending Now"]
    assert items[0]["art"] == "https://art.example/flux.png" and items[0]["playable"]
    assert items[0]["meta"] == _meta("FluxFM")  # unescaped back to the DIDL text
    assert not items[3]["playable"] and items[3]["art"] == ""
    text, ok = sc.apply("favorites")
    assert ok and "FluxFM (Sonos Radio)" in text and "Only in the Sonos app: Trending Now" in text


def test_play_radio_favorite_sets_uri_and_is_verified(favs: FakeSpeaker) -> None:
    text, ok = sc.apply("play_favorite", "flux")  # partial, any case
    assert ok and "Verified: YES" in text and "FluxFM" in text
    action, args = next(s for s in favs.sent if s[0] == "SetAVTransportURI")
    assert escape(RADIO[2]) in args and escape(_meta("FluxFM")) in args
    assert "RemoveAllTracksFromQueue" not in favs.calls


def test_play_playlist_favorite_goes_through_the_queue(favs: FakeSpeaker) -> None:
    text, ok = sc.apply("play_favorite", "My Shazam Tracks")
    assert ok
    assert favs.calls.index("RemoveAllTracksFromQueue") < favs.calls.index("AddURIToQueue")
    assert favs.uri == "x-rincon-queue:RINCON_TEST#0"


def test_favorite_by_service_name_and_fuzzy_name(favs: FakeSpeaker) -> None:
    assert sc.apply("play_favorite", "spotify")[1]
    assert "Shazam" in favs.sent[[s[0] for s in favs.sent].index("AddURIToQueue")][1]
    assert sc.apply("play_favorite", "fluxfn")[1]  # small typo


def test_favorite_errors(favs: FakeSpeaker) -> None:
    with pytest.raises(sc.SonosError, match="More than one"):
        sc.apply("play_favorite", "fm")
    with pytest.raises(sc.SonosError, match="No favorite named"):
        sc.apply("play_favorite", "zzzz")
    with pytest.raises(sc.SonosError, match="folder"):
        sc.apply("play_favorite", "Trending Now")
    with pytest.raises(sc.SonosError, match="needs the name"):
        sc.apply("play_favorite", "")


def test_tv_switches_to_the_tv_input(favs: FakeSpeaker) -> None:
    favs.uri = "x-sonosapi-stream:s1"
    text, ok = sc.apply("tv")
    assert ok and favs.uri == "x-sonos-htastream:RINCON_TEST:spdif"
    assert "Verified: YES" in text


def test_tool_passes_the_favorite_name(favs: FakeSpeaker) -> None:
    res = sc.SonosControlTool().execute(action="play_favorite", name="FluxFM")
    assert res.success and "FluxFM" in res.content
