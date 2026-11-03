"""Hue tools: matching, bridge client errors, read-back verdicts, approval gate."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from openjarvis.tools import hue_bridge
from openjarvis.tools.approval_store import (
    STATUS_APPROVED,
    STATUS_EXECUTED,
    TIER_HIGH,
    ApprovalStore,
)
from openjarvis.tools.hue_all_set import (
    FAILED,
    PARTLY,
    UNCONFIRMABLE,
    VERIFIED,
    HueAllSetTool,
    room_verdict,
)
from openjarvis.tools.hue_execute import HueExecuteTool
from openjarvis.tools.hue_light import (
    HueLightTool,
    find_lamp,
    hex_to_xy,
    lamp_capabilities,
    lamp_info,
    set_lamp,
    xy_to_hex,
)
from openjarvis.tools.hue_light_list import lamp_report
from openjarvis.tools.hue_lights import room_report
from openjarvis.tools.hue_propose import HUE_ROOM_POWER, HueProposeTool
from openjarvis.tools.hue_set import HueSetTool

from .conftest import GROUPS, LIGHTS


# ---------------------------------------------------------------------- room matching
@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("Kitchen", ("10", "Kitchen")),
        ("kitchens", ("10", "Kitchen")),
        ("hall", ("5", "Hallway")),
        ("the office lights", ("4", "Office")),
        ("sleep lights", ("1", "Sleep")),
        ("cocktail hallway", None),  # strict on purpose: never guess a room
        ("", None),
        ("Kitchen I", None),  # zones are not rooms
    ],
)
def test_find_room(spoken, expected):
    assert hue_bridge.find_room(GROUPS, spoken) == expected


def test_find_room_ambiguous_partial_is_refused():
    groups = {
        "1": {"type": "Room", "name": "Office A"},
        "2": {"type": "Room", "name": "Office B"},
    }
    assert hue_bridge.find_room(groups, "office") is None


def test_rooms_ignores_zones():
    assert [name for _gid, name in hue_bridge.rooms(GROUPS)] == [
        "Sleep",
        "Office",
        "Hallway",
        "Kitchen",
    ]


# ---------------------------------------------------------------------- bridge client
class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def key_file(tmp_path, monkeypatch):
    path = tmp_path / "hue-key.txt"
    path.write_text("secret-key\n", encoding="utf-8")
    monkeypatch.setattr(hue_bridge, "KEY_FILE", str(path))
    return path


def test_bridge_address_is_read_on_every_call(monkeypatch):
    monkeypatch.setenv("HUE_BRIDGE_IP", "10.0.0.2")
    assert hue_bridge.bridge_address() == "10.0.0.2"
    monkeypatch.setenv("HUE_BRIDGE_IP", " 10.0.0.3 ")
    assert hue_bridge.bridge_address() == "10.0.0.3"


def test_request_without_address_says_so(monkeypatch, key_file):
    monkeypatch.setattr(hue_bridge, "bridge_address", lambda: "")
    with pytest.raises(hue_bridge.HueBridgeError, match="no bridge address"):
        hue_bridge.request("/lights")


@pytest.mark.parametrize("addr", ["10.0.0.2/evil", "user@10.0.0.2", "file://x"])
def test_request_refuses_odd_addresses(monkeypatch, key_file, addr):
    monkeypatch.setattr(hue_bridge, "bridge_address", lambda: addr)
    with pytest.raises(hue_bridge.HueBridgeError, match="not a plain host"):
        hue_bridge.request("/lights")


def test_request_builds_url_and_reports_bridge_errors(monkeypatch, key_file):
    seen = []

    def fake_urlopen(req, timeout):
        seen.append((req.full_url, req.get_method(), req.data, timeout))
        return _Reply(
            json.dumps(
                [{"error": {"type": 1, "description": "unauthorized user"}}]
            ).encode()
        )

    monkeypatch.setattr(hue_bridge, "bridge_address", lambda: "10.0.0.2")
    monkeypatch.setattr(hue_bridge.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(hue_bridge.HueBridgeError, match="unauthorized user") as err:
        hue_bridge.request("/groups/4/action", {"on": True})
    assert seen == [
        (
            "http://10.0.0.2/api/secret-key/groups/4/action",
            "PUT",
            b'{"on": true}',
            hue_bridge.TIMEOUT,
        )
    ]
    assert hue_bridge.error_text(err.value) == "unauthorized user"
    assert (
        hue_bridge.error_text(OSError("http://10.0.0.2/api/secret-key")) == "OSError"
    )  # never leaks the key


def test_log_call_never_raises(monkeypatch):
    monkeypatch.setattr(hue_bridge, "LOG_FILE", "/nonexistent-dir/log.txt")
    hue_bridge.log_call("hue_set", {"room": "Kitchen"})


# ------------------------------------------------------------------------- room tools
def test_hue_set_switches_and_verifies(bridge):
    r = HueSetTool().execute(room="kitchen lights", state="on")
    assert r.success
    assert bridge.puts == [("/groups/10/action", {"on": True})]
    assert (
        "Sent: Kitchen on." in r.content
        and "Verified by reading back: YES" in r.content
    )


def test_hue_set_unknown_room_lists_rooms(bridge):
    r = HueSetTool().execute(room="garage", state="off")
    assert (
        not r.success
        and r.content == "No such room. Rooms: Sleep, Office, Hallway, Kitchen"
    )
    assert bridge.puts == []


def test_hue_set_rejects_bad_state(bridge):
    assert (
        HueSetTool().execute(room="Kitchen", state="dim").content
        == "state must be on or off."
    )


def test_hue_set_reports_bridge_reason(monkeypatch):
    def refuse(path, body=None):
        raise hue_bridge.HueBridgeError("unauthorized user")

    monkeypatch.setattr(hue_bridge, "request", refuse)
    r = HueSetTool().execute(room="Kitchen", state="on")
    assert not r.success and r.content == "Hue set error: unauthorized user"


@pytest.mark.parametrize(
    "ids, sent, verdict",
    [
        (["16", "17"], True, VERIFIED),
        (["1", "2"], True, PARTLY),  # Bed 4 is unreachable
        (["2"], True, UNCONFIRMABLE),
        (["16"], False, FAILED),
        (
            ["16", "99"],
            True,
            PARTLY,
        ),  # a lamp missing from /lights must not crash the report
    ],
)
def test_room_verdict(ids, sent, verdict):
    lights = json.loads(json.dumps(LIGHTS))
    for lid in ("1", "16", "17"):
        lights[lid]["state"]["on"] = True
    assert room_verdict("Room", ids, lights, sent, want_on=True)[0] == verdict


def test_room_verdict_mismatch():
    assert room_verdict("Kitchen", ["16"], LIGHTS, True, want_on=True)[0] == FAILED


def test_hue_all_set_counts_rooms(bridge):
    r = HueAllSetTool().execute(state="on")
    assert r.success
    assert r.content.splitlines()[0] == (
        "Requested all rooms on. 3 verified, 1 partly (some lights unreachable),"
        " 0 not confirmable (all lights unreachable), 0 failed."
    )
    assert len(bridge.puts) == 4  # rooms only, never the zone


def test_room_and_lamp_reports():
    assert (
        room_report(GROUPS, LIGHTS).splitlines()[0]
        == "Sleep: off - Bed 1 ct (off); Bed 4 ct (off, unreachable)"
    )
    lines = lamp_report(
        {**LIGHTS, "x7": {"name": "Odd", "state": {"on": False}}}
    ).splitlines()
    assert lines[0] == "id 1: Bed 1 ct - off" and lines[-1] == "id x7: Odd - off"
    assert "id 14: Hue filament - ON at 79%" in lines


# ----------------------------------------------------------------------- single lamps
def test_colour_conversion():
    assert hex_to_xy("#000000") == [0.3227, 0.329]
    x, y = hex_to_xy("#ff0000")
    assert x > 0.6 and y < 0.4
    assert xy_to_hex([0.3, 0.0]) == "#ffffff"
    back = xy_to_hex(
        hex_to_xy("#ff0000")
    )  # round trip keeps the colour (within rounding)
    assert int(back[1:3], 16) >= 0xF0 and back[3:] == "0000"


def test_lamp_capabilities_and_info():
    assert lamp_capabilities(LIGHTS["12"]) == {"dim": True, "color": True, "ct": True}
    assert lamp_capabilities(LIGHTS["14"]) == {"dim": True, "color": False, "ct": False}
    info = lamp_info("1", LIGHTS["1"])
    assert (
        info["name"] == "Bed 1 ct"
        and info["bri"] == 100
        and info["hex"] == "#ffd6a0"
        and info["ct"]
    )


@pytest.mark.parametrize(
    "name, room_ids, expected",
    [
        ("hue color desk", None, "12"),
        ("desk", None, "12"),
        ("the kitchen strip lamp", None, "17"),
        ("kitchen", None, None),  # two kitchen lamps: refuse instead of guessing
        ("bed", {"1"}, "1"),
    ],
)
def test_find_lamp(name, room_ids, expected):
    assert find_lamp(LIGHTS, name, room_ids) == expected


def test_set_lamp_body(bridge):
    set_lamp("12", bri=50, color="red", kelvin=None)
    path, body = bridge.puts[-1]
    assert (
        path == "/lights/12/state"
        and body["on"] is True
        and body["bri"] == 127
        and len(body["xy"]) == 2
    )
    set_lamp("16", on=False)
    assert bridge.puts[-1] == ("/lights/16/state", {"on": False})
    with pytest.raises(ValueError):
        set_lamp("12", color="mauve-ish")


def test_hue_light_tool(bridge):
    r = HueLightTool().execute(light="desk", brightness=40)
    assert r.success and "Now: ON, 40%" in r.content and "Verified: YES" in r.content
    r = HueLightTool().execute(light="Hue filament", color="blue")
    assert (
        not r.success and r.content == "Hue filament cannot show colours (white lamp)."
    )


def test_hue_light_room_narrows_ambiguous_name(bridge):
    assert not HueLightTool().execute(light="ct", state="on").success  # two "ct" lamps
    r = HueLightTool().execute(light="ct", room="sleep lights", state="on")
    assert not r.success  # both are in Sleep: still ambiguous, nothing switched
    assert bridge.puts == []
    r = HueLightTool().execute(light="strip", room="kitchen", state="on")
    assert r.success and bridge.puts == [("/lights/17/state", {"on": True})]


# ---------------------------------------------------------------------- approval gate
@pytest.fixture
def approvals(tmp_path, monkeypatch):
    db = str(tmp_path / "approvals.db")
    monkeypatch.setattr(
        "openjarvis.tools.hue_propose.ApprovalStore", lambda: ApprovalStore(db)
    )
    monkeypatch.setattr(
        "openjarvis.tools.hue_execute.ApprovalStore", lambda: ApprovalStore(db)
    )
    return db


def _request_id(text):
    return text.split()[1]


def test_propose_never_switches(bridge, approvals):
    r = HueProposeTool().execute(room="office lights", state="on")
    assert r.success and "Waiting for the user to approve" in r.content
    assert bridge.puts == []
    store = ApprovalStore(approvals)
    act = store.get_action(_request_id(r.content))
    store.close()
    assert act.action_type == HUE_ROOM_POWER and act.payload == {
        "group_id": "4",
        "room": "Office",
        "state": "on",
    }


def test_execute_refuses_unless_approved(bridge, approvals):
    rid = _request_id(HueProposeTool().execute(room="Office", state="on").content)
    assert (
        "not approved by the user" in HueExecuteTool().execute(request_id=rid).content
    )
    assert "not found" in HueExecuteTool().execute(request_id="nope").content
    assert HueExecuteTool().execute(request_id="").content == "No request id given."
    assert bridge.puts == []


def test_execute_runs_once_after_approval(bridge, approvals):
    rid = _request_id(HueProposeTool().execute(room="Office", state="on").content)
    store = ApprovalStore(approvals)
    store.update_status(rid, STATUS_APPROVED)
    store.close()
    r = HueExecuteTool().execute(request_id=rid)
    assert r.success and bridge.puts == [("/groups/4/action", {"on": True})]
    again = HueExecuteTool().execute(request_id=rid)
    assert (
        "is %s" % STATUS_EXECUTED in again.content and len(bridge.puts) == 1
    )  # no replay


def test_execute_refuses_expired_and_foreign_requests(bridge, approvals):
    store = ApprovalStore(approvals)
    old = store.queue_action(
        HUE_ROOM_POWER,
        "x",
        {"group_id": "4", "room": "Office", "state": "on"},
        HUE_ROOM_POWER,
        TIER_HIGH,
        ttl_hours=1,
    )
    other = store.queue_action("tado_set", "x", {}, "tado_set", TIER_HIGH)
    for rid in (old.id, other.id):
        store.update_status(rid, STATUS_APPROVED)
    store._conn.execute(  # move the expiry into the past
        "UPDATE pending_actions SET expires_at = ? WHERE id = ?",
        ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), old.id),
    )
    store._conn.commit()
    store.close()
    assert "has expired" in HueExecuteTool().execute(request_id=old.id).content
    assert (
        "is not a Hue request" in HueExecuteTool().execute(request_id=other.id).content
    )
    assert bridge.puts == []


def test_execute_reports_failed_read_back(bridge, approvals, monkeypatch):
    rid = _request_id(HueProposeTool().execute(room="Office", state="off").content)
    store = ApprovalStore(approvals)
    store.update_status(rid, STATUS_APPROVED)
    store.close()

    def no_read_back(group_id):
        raise OSError("timed out")

    monkeypatch.setattr(hue_bridge, "room_any_on", no_read_back)
    r = HueExecuteTool().execute(request_id=rid)
    assert (
        not r.success
        and r.content == "Sent: Office off. Could not read back (OSError)."
    )


def test_power_state_and_lookup_room(bridge):
    assert [hue_bridge.power_state(v) for v in ("on", " OFF ", "dim", None)] == [
        True,
        False,
        None,
        None,
    ]
    assert hue_bridge.lookup_room("office lights") == ("4", "Office")
    with pytest.raises(
        hue_bridge.UnknownRoom, match="Rooms: Sleep, Office, Hallway, Kitchen"
    ):
        hue_bridge.lookup_room("garage")
