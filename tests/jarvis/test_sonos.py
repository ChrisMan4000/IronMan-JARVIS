"""Tests for the Sonos tool. No speaker is needed: the SOAP call is replaced by a fake."""

from __future__ import annotations

import re

import pytest

from openjarvis.tools import sonos_control as sc


class FakeSpeaker:
    """Answers the few UPnP actions the tool uses and remembers what it was told."""

    def __init__(self) -> None:
        self.volume = 17
        self.muted = False
        self.state = "STOPPED"
        self.calls: list[str] = []

    def soap(self, service: tuple[str, str], action: str, args: str = "") -> str:
        self.calls.append(action)
        if action == "GetTransportInfo":
            return "<CurrentTransportState>%s</CurrentTransportState>" % self.state
        if action == "GetVolume":
            return "<CurrentVolume>%d</CurrentVolume>" % self.volume
        if action == "GetMute":
            return "<CurrentMute>%d</CurrentMute>" % int(self.muted)
        if action == "GetMediaInfo":
            return "<CurrentURI>x-sonos-htastream:RINCON_1:spdif</CurrentURI>"
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
