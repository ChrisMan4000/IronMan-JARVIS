"""Oxxify ventilation: Vento packets, change planning, rediscovery and the tool."""

from __future__ import annotations

import json

import pytest

from openjarvis.tools import oxxify_vent as ox


# ------------------------------------------------------------------------- protocol
def _reply(dev_id: str, func: int, data: bytes) -> bytes:
    """A unit's answer looks like a request with the answer function code."""
    return ox.build_packet(dev_id, "", func, data)


def test_packet_round_trip():
    raw = _reply("UNIT42", ox.F_RESPONSE, bytes([ox.P_POWER, 1, ox.P_SPEED, 3]))
    assert ox.parse_packet(raw) == (
        "UNIT42",
        ox.F_RESPONSE,
        {ox.P_POWER: b"\x01", ox.P_SPEED: b"\x03"},
    )


def test_broken_packets_are_ignored():
    raw = bytearray(_reply("UNIT42", ox.F_RESPONSE, bytes([ox.P_POWER, 1])))
    raw[-1] ^= 0xFF  # wrong checksum
    assert ox.parse_packet(bytes(raw)) is None
    assert ox.parse_packet(b"\x00\x01garbage") is None
    assert ox.parse_packet(b"") is None


def test_decode_params_pages_sizes_and_unknowns():
    data = bytes([0xFE, 3, ox.P_FILTER_LEFT, 0, 0, 90, 0xFD, 0x99, 0xFF, 0x01, 0x02, 7])
    assert ox._decode_params(data) == {ox.P_FILTER_LEFT: b"\x00\x00Z", 0x0102: b"\x07"}


# ------------------------------------------------------------------------- planning
@pytest.mark.parametrize(
    "words, mode",
    [
        ("heat recovery", 1),
        ("recovery ventilation", 1),
        ("supply air", 2),
        ("ventilation", 0),
        ("turbo", None),
    ],
)
def test_mode_from_words(words, mode):
    assert ox.mode_from_words(words) == mode


@pytest.mark.parametrize(
    "action, value, writes",
    [
        ("on", "", {ox.P_POWER: 1}),
        ("speed", "speed 2", {ox.P_POWER: 1, ox.P_SPEED: 2}),
        ("mode", "supply", {ox.P_POWER: 1, ox.P_MODE: 2}),
        ("timer_off", "", {ox.P_TIMER: 0}),
        ("party", "", {ox.P_POWER: 1, ox.P_TIMER: 2}),
        ("humidity", "64 %", {ox.P_HUM_ON: 1, ox.P_HUM_SET: 60}),
    ],
)
def test_plan_change(action, value, writes):
    plan = ox.plan_change(action, value)
    assert not isinstance(plan, str) and plan[0] == writes


@pytest.mark.parametrize(
    "action, value, error",
    [
        ("speed", "4", "Speed must be 1, 2 or 3."),
        ("mode", "turbo", "Mode must be ventilation, heat recovery or supply air."),
        ("humidity", "95", "Humidity target must be between 40 and 80 percent."),
        ("dance", "", "Unknown action."),
    ],
)
def test_plan_change_refusals(action, value, error):
    plan = ox.plan_change(action, value)
    assert isinstance(plan, str) and plan.startswith(error)


def test_describe():
    st = _status(
        power=True,
        speed=2,
        timer="night",
        humidity=48,
        fan_rpm=900,
        filter_days_left=30,
    )
    assert ox.describe(st, "Vent") == (
        "Vent: ON, speed 2, mode heat recovery, night timer running, room humidity 48%,"
        " fan 900 rpm, filter due in 30 days"
    )
    assert ox.describe(_status(power=False)) == "Ventilation: OFF"


def _status(**changes) -> ox.VentStatus:
    st: ox.VentStatus = {
        "power": True,
        "speed": 1,
        "mode": "heat recovery",
        "timer": "off",
        "boost": False,
        "humidity": None,
        "humidity_sensor_on": False,
        "humidity_target": None,
        "fan_rpm": 0,
        "filter_days_left": None,
        "filter_due": False,
        "alarm": "none",
    }
    st.update(changes)  # type: ignore[typeddict-item]
    return st


# ------------------------------------------------------------------------- settings
@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "oxxify.json"
    path.write_text(json.dumps({"ip": "10.0.0.5", "id": "UNIT42"}), encoding="utf-8")
    monkeypatch.setattr(ox, "CFG_FILE", str(path))
    monkeypatch.setattr(ox, "LOG_FILE", str(tmp_path / "log.txt"))
    return path


def test_load_cfg_fills_defaults(cfg_file):
    assert ox.load_cfg() == {
        "ip": "10.0.0.5",
        "id": "UNIT42",
        "password": "1111",
        "name": "Ventilation",
    }


def test_rediscovery_saves_the_new_address(cfg_file, monkeypatch):
    monkeypatch.setattr(
        ox, "discover", lambda pwd: [("10.0.0.9", "OTHER"), ("10.0.0.7", "UNIT42")]
    )
    seen = []

    def fn(ip):
        seen.append(ip)
        if ip == "10.0.0.5":
            raise OSError("no answer")
        return "ok"

    cfg = ox.load_cfg()
    assert ox.call_with_rediscovery(cfg, fn) == "ok"
    assert seen == ["10.0.0.5", "10.0.0.7"]
    assert json.loads(cfg_file.read_text())["ip"] == "10.0.0.7"


def test_rediscovery_gives_up_when_the_unit_is_gone(cfg_file, monkeypatch):
    monkeypatch.setattr(ox, "discover", lambda pwd: [])
    with pytest.raises(OSError):
        ox.call_with_rediscovery(
            ox.load_cfg(), lambda ip: (_ for _ in ()).throw(OSError("silent"))
        )


# ------------------------------------------------------------------------- the tool
class FakeUnit:
    """Stands in for _udp_request: keeps parameter values and answers reads."""

    def __init__(self, ignore_writes: bool = False) -> None:
        self.params = {ox.P_POWER: 1, ox.P_SPEED: 1, ox.P_MODE: 1, ox.P_TIMER: 0}
        self.ignore_writes = ignore_writes
        self.writes: list[bytes] = []

    def __call__(self, ip, dev_id, pwd, func, data, timeout=2.0, broadcast=False):
        if func == ox.F_WRITE:
            self.writes.append(data)
            if not self.ignore_writes:
                for i in range(0, len(data), 2):
                    self.params[data[i]] = data[i + 1]
            return []
        return [
            (ip, dev_id, {k: bytes([v]) for k, v in self.params.items() if k in data})
        ]


@pytest.fixture
def unit(cfg_file, monkeypatch):
    fake = FakeUnit()
    monkeypatch.setattr(ox, "_udp_request", fake)
    monkeypatch.setattr(ox.time, "sleep", lambda _s: None)
    return fake


def test_tool_changes_and_verifies(unit):
    r = ox.OxxifyVentTool().execute(action="speed", value="3")
    assert r.success and r.content.endswith("Verified: YES")
    assert unit.writes == [bytes([ox.P_POWER, 1, ox.P_SPEED, 3])]


def test_tool_reports_unconfirmed_change_as_failure(unit):
    unit.ignore_writes = True
    r = ox.OxxifyVentTool().execute(action="off")
    assert not r.success and r.content.endswith("Verified: NO")


def test_tool_status_and_refusals(unit):
    assert (
        ox.OxxifyVentTool()
        .execute(action="status")
        .content.startswith("Ventilation: ON, speed 1")
    )
    r = ox.OxxifyVentTool().execute(action="speed", value="9")
    assert not r.success and unit.writes == []


def test_tool_without_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(ox, "CFG_FILE", str(tmp_path / "missing.json"))
    r = ox.OxxifyVentTool().execute(action="status")
    assert not r.success and "not set up yet" in r.content


def test_tool_wrong_password(unit, monkeypatch):
    def refuse(*args, **kwargs):
        raise ox.AuthError("wrong password")

    monkeypatch.setattr(ox, "_udp_request", refuse)
    assert "refused the password" in ox.OxxifyVentTool().execute(action="on").content
