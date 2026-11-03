"""World map of the hardware helper: where this PC's open internet connections go.

Every 5 seconds netstat lists the established TCP connections; each new public
address is looked up once in the offline DB-IP database next to this file (no
data leaves this PC). The result is helper_stats.live["conns"].
"""

from __future__ import annotations

import ipaddress
import logging
import os
import subprocess  # nosec B404 - only netstat, by full path
import threading
from typing import Any

from helper_stats import every, live, program

try:  # optional: without it the map simply shows no dots
    import maxminddb
except ImportError:
    maxminddb = None

logger = logging.getLogger(__name__)

GEO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dbip.mmdb")
CONN_EVERY = 5  # seconds between connection checks


def public_ips(netstat_output: str) -> dict[str, int]:
    """Public IPs with established TCP connections, with a count each."""
    ips: dict[str, int] = {}
    for line in netstat_output.splitlines():
        p = line.split()
        if len(p) >= 4 and p[0] == "TCP" and p[3] == "ESTABLISHED":
            ip = p[2].rsplit(":", 1)[0].strip("[]")
            try:
                a = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if a.is_private or a.is_loopback or a.is_link_local or a.is_multicast:
                continue
            ips[ip] = ips.get(ip, 0) + 1
    return ips


def locate(record: dict[str, Any] | None) -> dict[str, Any]:
    """Map entry from one location record ({"bad": 1} when it has no position)."""
    r = record or {}
    loc = r.get("location") or {}
    if "latitude" not in loc or "longitude" not in loc:
        return {"bad": 1}
    return {
        "lat": loc["latitude"],
        "lon": loc["longitude"],
        "country": (r.get("country") or {}).get("names", {}).get("en", ""),
        "city": (r.get("city") or {}).get("names", {}).get("en", ""),
        "org": "",
    }


class GeoCache:
    """Location of every address seen so far (looked up once, kept for the run)."""

    def __init__(self, db_path: str = GEO_DB) -> None:
        self.places: dict[str, dict[str, Any]] = {}
        self._reader: Any = None
        if maxminddb is None:
            logger.debug("maxminddb not installed: the world map shows no dots")
            return
        try:
            self._reader = maxminddb.open_database(db_path)
        except (OSError, ValueError) as exc:
            logger.debug("no location database, the map shows no dots: %s", exc)
            self._reader = None

    def look_up(self, ips: list[str]) -> None:
        for ip in ips:
            try:
                record = self._reader.get(ip) if self._reader else None
            except ValueError:  # not an address the database understands
                record = None
            self.places[ip] = locate(record)

    def map_dots(self, ips: dict[str, int]) -> list[dict[str, Any]]:
        """The map dots: one per located address, with its connection count."""
        out = []
        for ip, n in ips.items():
            place = self.places.get(ip, {})
            if "lat" in place:
                out.append({"ip": ip, "n": n, **place})
        return out

    def step(self) -> None:
        """Refresh the connection list for the map."""
        output = subprocess.check_output(  # nosec B603 - fixed program and arguments
            [program("netstat"), "-n", "-p", "tcp"], text=True, timeout=8
        )
        ips = public_ips(output)
        self.look_up([i for i in ips if i not in self.places])
        live.set("conns", self.map_dots(ips))


def start() -> None:
    """Start the connection loop in the background."""
    cache = GeoCache()
    threading.Thread(target=every(CONN_EVERY, cache.step), daemon=True).start()
