"""Set up and test the Oxxify ventilation (local Wi-Fi, no cloud).

  uv run --no-sync python tools\\oxxify.py <command>

Commands:
  setup     find the unit, ask for its password, save oxxify.json
  status    show what the unit is doing (the default)
  discover  list the units on the home network
  debug     show how the unit answers single questions

The password is the one set in the Oxxify / impruf app (factory default 1111).
It is saved in ~/.openjarvis/oxxify.json and never printed.
"""

from __future__ import annotations

import getpass
import sys
from collections.abc import Callable

from openjarvis.tools.oxxify_protocol import (
    DEFAULT_PASSWORD,
    F_READ,
    AuthError,
    discover,
    parse_packet,
    probe,
    read_status,
)
from openjarvis.tools.oxxify_vent import (
    DEFAULT_NAME,
    describe,
    load_cfg,
    read_configured_status,
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


class StopCommand(Exception):
    """Ends a command with a message for the user (main prints it, exit code 1)."""


def ask_password() -> str:
    prompt = "Unit password from the app (Enter = %s): " % DEFAULT_PASSWORD
    return getpass.getpass(prompt) or DEFAULT_PASSWORD


def find_units(missing: str) -> list[tuple[str, str]]:
    """(ip, id) of every unit on the home network; StopCommand(missing) if none."""
    units = discover()
    if not units:
        raise StopCommand(missing)
    return units


def pick_unit(units: list[tuple[str, str]]) -> tuple[str, str]:
    """The only unit, or the one the user picks by number."""
    if len(units) == 1:
        return units[0]
    for i, (ip, did) in enumerate(units, 1):
        print("%d) %s  id %s" % (i, ip, did))
    answer = input("Which one? ") or "1"
    if not answer.isdigit() or not 1 <= int(answer) <= len(units):
        raise StopCommand("No unit number %r. Run setup again." % answer)
    return units[int(answer) - 1]


def debug_answer(raw: bytes | None) -> str:
    """One unit answer, decoded as far as possible."""
    if raw is None:
        return "no answer"
    reply = parse_packet(raw)
    if not reply:
        return "unreadable answer, %d bytes" % len(raw)
    fields = {hex(k): v.hex() for k, v in reply[2].items()}
    return "func %02x data %s" % (reply[1], fields)


def cmd_discover(_args: list[str]) -> None:
    units = discover()
    if not units:
        print("No Oxxify unit answered on the home network.")
    for ip, did in units:
        print("%s  id %s" % (ip, did))


def cmd_debug(_args: list[str]) -> None:
    ip, did = find_units("No Oxxify unit answered on the home network.")[0]
    pwd = ask_password()
    print("unit %s id %s" % (ip, did))
    for label, data in DEBUG_QUESTIONS:
        print("%-18s -> %s" % (label, debug_answer(probe(ip, did, pwd, F_READ, data))))


def cmd_setup(args: list[str]) -> None:
    """setup [password]: find the unit, check the password, save oxxify.json."""
    units = find_units("No Oxxify unit answered. Is it on the same Wi-Fi as this PC?")
    ip, did = pick_unit(units)
    print("Found the unit at %s (id %s)." % (ip, did))
    pwd = args[0] if args else ask_password()
    try:
        st = read_status(ip, did, pwd)
    except AuthError as exc:
        raise StopCommand(
            "Wrong password. Look it up in the Oxxify app (device settings) and run"
            " setup again."
        ) from exc
    save_cfg({"ip": ip, "id": did, "password": pwd, "name": DEFAULT_NAME})
    print("Saved. " + describe(st))


def cmd_status(_args: list[str]) -> None:
    cfg = load_cfg()
    print(describe(read_configured_status(cfg), cfg["name"]))


COMMANDS: dict[str, Callable[[list[str]], None]] = {
    "discover": cmd_discover,
    "debug": cmd_debug,
    "setup": cmd_setup,
    "status": cmd_status,
}


def main(argv: list[str]) -> int:
    """Run one command (unknown names show the status); returns the exit code."""
    cmd = argv[1] if len(argv) > 1 else "status"
    try:
        COMMANDS.get(cmd, cmd_status)(argv[2:])
    except StopCommand as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
