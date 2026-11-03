"""Tado heating: input checks, zone matching, read-back verdicts and the tool."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from openjarvis.tools import tado_heating as tado


def _zone(zid, name, target=20.0, overlay=False, power="ON"):
    z = SimpleNamespace(
        name=name,
        current_temp=19.5,
        target_temp=target,
        power=SimpleNamespace(value=power),
        heating_power_percentage=10,
        overlay_active=overlay,
        open_window=False,
        available=True,
    )
    z._id = zid
    return z


ZONES = [
    _zone(1, "Living Room"),
    _zone(2, "Kitchen"),
    _zone(3, "Bathroom"),
    _zone(4, "Temp Sensor"),
]


@pytest.mark.parametrize(
    "value, ok",
    [
        (4.9, False),
        (5, True),
        (21.5, True),
        (25, True),
        (25.1, False),
        (math.nan, False),
        (math.inf, False),
        ("20", False),
        (None, False),
    ],
)
def test_valid_temp(value, ok):
    assert tado._valid_temp(value) is ok


@pytest.mark.parametrize(
    "spoken, name",
    [
        ("kitchen", "Kitchen"),
        ("the kitchen radiators", "Kitchen"),
        ("living", "Living Room"),
        ("bath", "Bathroom"),
    ],
)
def test_find_zone(spoken, name):
    zone, why = tado.find_zone(ZONES, spoken)
    assert zone.name == name and why == ""


def test_find_zone_refuses_unknown_and_ambiguous():
    assert tado.find_zone(ZONES, "garage") == (
        None,
        "No such zone. Zones: Living Room, Kitchen, Bathroom, Temp Sensor",
    )
    twins = [_zone(1, "Office"), _zone(2, "Office")]
    assert tado.find_zone(twins, "office")[1].startswith(
        "Several zones share that name."
    )


def test_matches():
    assert tado.matches("set", _zone(1, "K", target=21.0, overlay=True), 21.0)
    assert not tado.matches("set", _zone(1, "K", target=20.0, overlay=True), 21.0)
    assert tado.matches("off", _zone(1, "K", power="OFF"), None)
    assert tado.matches("resume", _zone(1, "K", overlay=False), None)


class FakeTado:
    """Stands in for the logged-in PyTado client; applies changes after `lag` reads."""

    def __init__(self, lag: int = 0) -> None:
        self.zones = {z._id: _zone(z._id, z.name) for z in ZONES}
        self.lag, self.pending, self.calls = lag, None, []

    def get_zones(self):
        if self.pending and self.lag <= 0:
            zid, changes = self.pending
            vars(self.zones[zid]).update(changes)
            self.pending = None
        self.lag -= 1
        return list(self.zones.values())

    def set_zone_overlay(self, zid, mode, set_temp=None, power=None, duration=None):
        self.calls.append(("overlay", zid, set_temp, power))
        if power is not None:
            self.pending = (
                zid,
                {"power": SimpleNamespace(value="OFF"), "overlay_active": True},
            )
        else:
            self.pending = (zid, {"target_temp": set_temp, "overlay_active": True})

    def reset_zone_overlay(self, zid):
        self.calls.append(("reset", zid))
        self.pending = (zid, {"overlay_active": False})


@pytest.fixture
def fake(monkeypatch, tmp_path):
    pytest.importorskip("PyTado")
    client = FakeTado()
    monkeypatch.setattr(tado, "open_tado_api", lambda: client)
    monkeypatch.setattr(tado.time, "sleep", lambda _s: None)
    monkeypatch.setattr(tado, "LOG_FILE", str(tmp_path / "log.txt"))
    return client


def test_set_is_verified(fake):
    r = tado.TadoHeatingTool().execute(action="set", room="kitchen", temperature=21)
    assert r.success and "Verified: YES" in r.content
    assert fake.calls == [("overlay", 2, 21.0, None)]


def test_slow_cloud_is_read_back_again(fake):
    fake.lag = 2  # the change shows up on the third read-back
    assert tado.TadoHeatingTool().execute(action="resume", room="bathroom").success


def test_unconfirmed_change_is_a_failure(fake):
    fake.lag = 99
    r = tado.TadoHeatingTool().execute(action="off", room="Living Room")
    assert not r.success and "Verified: NO" in r.content


@pytest.mark.parametrize(
    "params, error",
    [
        ({"action": "set", "room": "kitchen"}, "Temperature missing."),
        (
            {"action": "set", "room": "kitchen", "temperature": 30},
            "Temperature must be between 5.0 and 25.0 C.",
        ),
        (
            {"action": "boost", "room": "kitchen", "minutes": 500},
            "Minutes must be between 5 and 120.",
        ),
        (
            {"action": "warp", "room": "kitchen"},
            "Unknown action. Use status, set, boost, off or resume.",
        ),
    ],
)
def test_bad_inputs_send_nothing(fake, params, error):
    r = tado.TadoHeatingTool().execute(**params)
    assert not r.success and r.content == error and fake.calls == []


def test_status_lists_every_zone(fake):
    lines = tado.TadoHeatingTool().execute(action="status").content.splitlines()
    assert len(lines) == 4 and lines[0].startswith(
        "Living Room: now 19.5 C, target 20.0 C, power ON"
    )
