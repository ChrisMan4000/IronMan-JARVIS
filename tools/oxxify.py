"""Set up and test the Oxxify ventilation (local Wi-Fi, no cloud).

  uv run --no-sync python tools\\oxxify.py setup     finds the unit, asks for its password, saves ~/.openjarvis/oxxify.json
  uv run --no-sync python tools\\oxxify.py status    shows what the unit is doing
  uv run --no-sync python tools\\oxxify.py discover  lists units on the home network

The password is the one set in the Oxxify / impruf app (factory default 1111).
"""
import getpass
import sys

from openjarvis.tools.oxxify_vent import AuthError, describe, discover, load_cfg, read_status, save_cfg

cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
if cmd == "discover":
    units = discover()
    print("\n".join("%s  id %s" % u for u in units) if units else "No Oxxify unit answered on the home network.")
elif cmd == "debug":
    # shows how the unit answers single questions; the password itself is never printed
    import socket
    from openjarvis.tools.oxxify_vent import _packet, _parse
    ip, did = discover()[0]
    pwd = getpass.getpass("Unit password (Enter = 1111): ") or "1111"
    print("unit %s id %s, password length %d" % (ip, did, len(pwd)))
    for label, func, data in [("power", 1, b"\x01"), ("speed", 1, b"\x02"), ("mode", 1, b"\xb7"),
                              ("humidity", 1, b"\x25"), ("power+speed", 1, b"\x01\x02"),
                              ("filter (3 bytes)", 1, b"\x64"), ("fan rpm (2 bytes)", 1, b"\x4a")]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2)
        s.sendto(_packet(did, pwd, func, data), (ip, 4000))
        try:
            raw, _ = s.recvfrom(1024); r = _parse(raw)
            print("%-18s -> %s" % (label, ("func %02x data %s" % (r[1], {hex(k): v.hex() for k, v in r[2].items()})) if r else "unreadable answer, %d bytes" % len(raw)))
        except socket.timeout:
            print("%-18s -> no answer" % label)
        s.close()
elif cmd == "setup":
    units = discover()
    if not units:
        sys.exit("No Oxxify unit answered. Is it on the same Wi-Fi as this PC?")
    ip, did = units[0]
    if len(units) > 1:
        for i, u in enumerate(units, 1):
            print("%d) %s  id %s" % (i, u[0], u[1]))
        ip, did = units[int(input("Which one? ") or 1) - 1]
    print("Found the unit at %s (id %s)." % (ip, did))
    pwd = sys.argv[2] if len(sys.argv) > 2 else (getpass.getpass("Unit password from the app (Enter = 1111): ") or "1111")
    try:
        st = read_status(ip, did, pwd)
    except AuthError:
        sys.exit("Wrong password. Look it up in the Oxxify app (device settings) and run setup again.")
    save_cfg({"ip": ip, "id": did, "password": pwd, "name": "Ventilation"})
    print("Saved. " + describe(st))
else:
    c = load_cfg()
    print(describe(read_status(c["ip"], c["id"], c.get("password", "1111")), c.get("name", "Ventilation")))
