"""Set up and test the Oxxify ventilation (local Wi-Fi, no cloud).

  uv run --no-sync python tools\\oxxify.py setup     finds the unit, asks for its
                                                    password, saves oxxify.json
  uv run --no-sync python tools\\oxxify.py status    shows what the unit is doing
  uv run --no-sync python tools\\oxxify.py discover  lists units on the home network
  uv run --no-sync python tools\\oxxify.py debug     shows how the unit answers
                                                    single questions

The password is the one set in the Oxxify / impruf app (factory default 1111).
It is saved in ~/.openjarvis/oxxify.json and never printed.
"""

import getpass
import sys

from openjarvis.tools.oxxify_vent import (
    DEFAULT_NAME,
    DEFAULT_PASSWORD,
    F_READ,
    AuthError,
    describe,
    discover,
    load_cfg,
    parse_packet,
    probe,
    read_configured_status,
    read_status,
    save_cfg,
)

DEBUG_QUESTIONS = [
    ("power", b"\x01"),
    ("speed", b"\x02"),
    ("mode", b"\xb7"),
    ("humidity", b"\x25"),
    ("power+speed", b"\x01\x02"),
    ("filter (3 bytes)", b"\x64"),
    ("fan rpm (2 bytes)", b"\x4a"),
]


def ask_password() -> str:
    prompt = "Unit password from the app (Enter = %s): " % DEFAULT_PASSWORD
    return getpass.getpass(prompt) or DEFAULT_PASSWORD


def cmd_discover() -> None:
    units = discover()
    if not units:
        print("No Oxxify unit answered on the home network.")
    for ip, did in units:
        print("%s  id %s" % (ip, did))


def cmd_debug() -> None:
    units = discover()
    if not units:
        sys.exit("No Oxxify unit answered on the home network.")
    ip, did = units[0]
    pwd = ask_password()
    print("unit %s id %s, password length %d" % (ip, did, len(pwd)))
    for label, data in DEBUG_QUESTIONS:
        raw = probe(ip, did, pwd, F_READ, data)
        if raw is None:
            answer = "no answer"
        else:
            reply = parse_packet(raw)
            answer = (
                "func %02x data %s"
                % (reply[1], {hex(k): v.hex() for k, v in reply[2].items()})
                if reply
                else "unreadable answer, %d bytes" % len(raw)
            )
        print("%-18s -> %s" % (label, answer))


def cmd_setup(password_arg: str | None) -> None:
    units = discover()
    if not units:
        sys.exit("No Oxxify unit answered. Is it on the same Wi-Fi as this PC?")
    ip, did = units[0]
    if len(units) > 1:
        for i, (u_ip, u_id) in enumerate(units, 1):
            print("%d) %s  id %s" % (i, u_ip, u_id))
        ip, did = units[int(input("Which one? ") or 1) - 1]
    print("Found the unit at %s (id %s)." % (ip, did))
    pwd = password_arg or ask_password()
    try:
        st = read_status(ip, did, pwd)
    except AuthError:
        sys.exit(
            "Wrong password. Look it up in the Oxxify app (device settings) and run"
            " setup again."
        )
    save_cfg({"ip": ip, "id": did, "password": pwd, "name": DEFAULT_NAME})
    print("Saved. " + describe(st))


def cmd_status() -> None:
    cfg = load_cfg()
    print(describe(read_configured_status(cfg), cfg["name"]))


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "discover":
        cmd_discover()
    elif cmd == "debug":
        cmd_debug()
    elif cmd == "setup":
        cmd_setup(argv[2] if len(argv) > 2 else None)
    else:
        cmd_status()


if __name__ == "__main__":
    main(sys.argv)
