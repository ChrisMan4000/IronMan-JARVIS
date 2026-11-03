"""The Blauberg Vento UDP protocol of the Oxxify smart 50 units (local Wi-Fi only).

Packets, discovery and the status read. The Jarvis tool on top of it (settings,
plain-language changes, read-back) is oxxify_vent.py.
"""

from __future__ import annotations

import socket
from typing import TypedDict

PORT = 4000
DEFAULT_ID = "DEFAULT_DEVICEID"
DEFAULT_PASSWORD = "1111"  # factory default of the Oxxify / impruf app

# Vento function codes (first byte after the password) and parameter numbers.
F_READ, F_WRITE, F_RESPONSE, F_AUTH_FAIL = 0x01, 0x02, 0x06, 0x07
P_POWER, P_SPEED, P_BOOST, P_TIMER = 0x01, 0x02, 0x06, 0x07
P_HUM_ON, P_HUM_SET, P_HUM = 0x0F, 0x19, 0x25
P_MANUAL, P_FAN1, P_FAN2 = 0x44, 0x4A, 0x4B
P_FILTER_LEFT, P_DEVID, P_ALARM, P_FILTER_DUE, P_MODE = 0x64, 0x7C, 0x83, 0x88, 0xB7
STATUS_PARAMS = bytes(
    [
        P_POWER,
        P_SPEED,
        P_BOOST,
        P_TIMER,
        P_HUM_ON,
        P_HUM_SET,
        P_HUM,
        P_MANUAL,
        P_FAN1,
        P_FAN2,
        P_FILTER_LEFT,
        P_ALARM,
        P_FILTER_DUE,
        P_MODE,
    ]
)

MODES = {0: "ventilation", 1: "heat recovery", 2: "supply air"}
TIMERS = {0: "off", 1: "night", 2: "party"}
ALARMS = {0: "none", 1: "alarm", 2: "warning"}

Answer = tuple[str, str, dict[int, bytes]]  # (ip, device id, {param: value bytes})


class AuthError(Exception):
    """The unit answered, but refused the password."""


class VentStatus(TypedDict):
    power: bool
    speed: int  # 1-3, 255 = manual
    mode: str
    timer: str
    boost: bool
    humidity: int | None
    humidity_sensor_on: bool
    humidity_target: int | None
    fan_rpm: int
    filter_days_left: int | None
    filter_due: bool
    alarm: str


# ---------------------------------------------------------------------------- protocol
def build_packet(dev_id: str, pwd: str, func: int, data: bytes) -> bytes:
    """One Vento request: header, device id, password, function, data, checksum."""
    body = (
        bytes([0x02, len(dev_id)])
        + dev_id.encode()
        + bytes([len(pwd)])
        + pwd.encode()
        + bytes([func])
        + data
    )
    checksum = sum(body) & 0xFFFF
    return b"\xfd\xfd" + body + bytes([checksum & 0xFF, checksum >> 8])


def _decode_params(data: bytes) -> dict[int, bytes]:
    """Parameter block -> {param: value bytes} (0xFF page, 0xFE size, 0xFD skip)."""
    out: dict[int, bytes] = {}
    i, page, size = 0, 0, 1
    while i < len(data):
        b = data[i]
        if b == 0xFF:  # next parameters are on another page
            page = data[i + 1] << 8
            i += 2
        elif b == 0xFE:  # next value is longer than one byte
            size = data[i + 1]
            i += 2
        elif b == 0xFD:  # the unit does not know this parameter
            i += 2
        else:
            out[page | b] = data[i + 1 : i + 1 + size]
            i += 1 + size
            size = 1
    return out


def parse_packet(raw: bytes) -> tuple[str, int, dict[int, bytes]] | None:
    """(device id, function, {param: bytes}), or None for a broken or foreign answer."""
    if len(raw) < 8 or raw[0] != 0xFD or raw[1] != 0xFD:
        return None
    if (sum(raw[2:-2]) & 0xFFFF) != raw[-2] | (raw[-1] << 8):
        return None
    i = 3
    n = raw[i]
    dev_id = raw[i + 1 : i + 1 + n].decode(errors="replace")
    i += 1 + n
    i += 1 + raw[i]  # skip the password echo
    func = raw[i]
    return dev_id, func, _decode_params(raw[i + 1 : -2])


def probe(
    ip: str, dev_id: str, pwd: str, func: int, data: bytes, timeout: float = 2.0
) -> bytes | None:
    """Send one request and return the raw answer, or None if the unit stays silent."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(build_packet(dev_id, pwd, func, data), (ip, PORT))
        try:
            return s.recvfrom(1024)[0]
        except socket.timeout:
            return None


def udp_request(
    ip: str,
    dev_id: str,
    pwd: str,
    func: int,
    data: bytes,
    timeout: float = 2.0,
    broadcast: bool = False,
) -> list[Answer]:
    """Send a request; return the readable answers (one unit, or all on broadcast).

    Raises AuthError when a single unit refuses the password. Silence is an empty list.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        if broadcast:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        s.sendto(build_packet(dev_id, pwd, func, data), (ip, PORT))
        answers: list[Answer] = []
        while True:
            try:
                raw, addr = s.recvfrom(1024)
            except socket.timeout:
                break
            reply = parse_packet(raw)
            if reply:
                if reply[1] == F_AUTH_FAIL and not broadcast:
                    raise AuthError("wrong password")
                if reply[1] == F_RESPONSE:
                    answers.append((addr[0], reply[0], reply[2]))
            if not broadcast:
                break
        return answers


def discover(
    pwd: str = DEFAULT_PASSWORD, timeout: float = 3.0
) -> list[tuple[str, str]]:
    """Units on the home network: [(ip, device_id)]."""
    found = {}
    ask = bytes([P_DEVID])
    for ip, _, prm in udp_request(
        "255.255.255.255", DEFAULT_ID, pwd, F_READ, ask, timeout, broadcast=True
    ):
        did = prm.get(P_DEVID, b"").decode(errors="replace").strip("\x00")
        if did:
            found[ip] = did
    return sorted(found.items())


def _le_int(b: bytes | None) -> int:
    return int.from_bytes(b, "little") if b else 0


def _read_params(ip: str, dev_id: str, pwd: str) -> dict[int, bytes]:
    answers = udp_request(ip, dev_id, pwd, F_READ, STATUS_PARAMS, timeout=1.0)
    if answers:
        return answers[0][2]
    # Some units stay silent when one asked number is unknown to them: ask one by one.
    params: dict[int, bytes] = {}
    for k in STATUS_PARAMS:
        single = udp_request(ip, dev_id, pwd, F_READ, bytes([k]), timeout=0.6)
        if single:
            params.update(single[0][2])
    if P_POWER not in params:
        raise OSError("no answer")
    return params


def read_status(ip: str, dev_id: str, pwd: str) -> VentStatus:
    """What the unit is doing now. Raises OSError when it does not answer."""
    p = _read_params(ip, dev_id, pwd)
    filter_left = p.get(P_FILTER_LEFT, b"")
    return {
        "power": _le_int(p.get(P_POWER)) == 1,
        "speed": _le_int(p.get(P_SPEED)),
        "mode": MODES.get(_le_int(p.get(P_MODE)), "unknown"),
        "timer": TIMERS.get(_le_int(p.get(P_TIMER)), "unknown"),
        "boost": _le_int(p.get(P_BOOST)) == 1,
        "humidity": _le_int(p.get(P_HUM)) if P_HUM in p else None,
        "humidity_sensor_on": _le_int(p.get(P_HUM_ON)) == 1,
        "humidity_target": _le_int(p.get(P_HUM_SET)) if P_HUM_SET in p else None,
        "fan_rpm": max(_le_int(p.get(P_FAN1)), _le_int(p.get(P_FAN2))),
        "filter_days_left": filter_left[2] if len(filter_left) >= 3 else None,
        "filter_due": _le_int(p.get(P_FILTER_DUE)) == 1,
        "alarm": ALARMS.get(_le_int(p.get(P_ALARM)), "unknown"),
    }
