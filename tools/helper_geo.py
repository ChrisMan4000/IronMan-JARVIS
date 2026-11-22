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
import time
from collections.abc import Iterator
from typing import Any

from helper_stats import every, live, program

try:  # optional: without it the map simply shows no dots
    import maxminddb
except ImportError:
    maxminddb = None

logger = logging.getLogger(__name__)

GEO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dbip.mmdb")
CONN_EVERY = 5  # seconds between connection checks


def _public_established(netstat_output: str) -> Iterator[tuple[str, int]]:
    """(public IP, owning process id) for each established TCP line of `netstat -o`.

    Lines without a process id give id 0.
    """
    for line in netstat_output.splitlines():
        p = line.split()
        if len(p) < 4 or p[0] != "TCP" or p[3] != "ESTABLISHED":
            continue
        ip = p[2].rsplit(":", 1)[0].strip("[]")
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_private or a.is_loopback or a.is_link_local or a.is_multicast:
            continue
        yield ip, int(p[4]) if len(p) > 4 and p[4].isdigit() else 0


def public_ips(netstat_output: str) -> dict[str, int]:
    """Public IPs with established TCP connections, with a count each."""
    ips: dict[str, int] = {}
    for ip, _pid in _public_established(netstat_output):
        ips[ip] = ips.get(ip, 0) + 1
    return ips


def public_conns(netstat_output: str) -> list[tuple[str, int]]:
    """(public IP, owning process id) of every established TCP connection."""
    return list(_public_established(netstat_output))


JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).lower()
_pid_cache: dict[str, Any] = {"t": 0.0, "pids": frozenset()}
_pid_lock = threading.Lock()


def jarvis_pids() -> frozenset[int]:
    """Process ids that run from the Jarvis folder (server, helper, wake word, Vite).

    Refreshed at most every 10 seconds. Empty when psutil is not installed.
    Returns an immutable snapshot, so callers cannot change the cache.
    """
    with _pid_lock:
        now = time.monotonic()
        if now - _pid_cache["t"] < 10:
            return _pid_cache["pids"]
        pids = _scan_jarvis_pids()
        _pid_cache["t"] = now
        _pid_cache["pids"] = pids
        return pids


def _scan_jarvis_pids() -> frozenset[int]:
    """Look at every process once (slow; jarvis_pids caches the answer)."""
    pids: set[int] = set()
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        for proc in psutil.process_iter(["pid", "exe", "cmdline"]):
            try:
                text = " ".join([proc.info.get("exe") or "", *(proc.info.get("cmdline") or [])])
            except Exception:  # noqa: BLE001 - a process may vanish while we look
                continue
            if JARVIS_ROOT in text.lower():
                pids.add(proc.info["pid"])
    return frozenset(pids)


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

    def map_dots(
        self, ips: dict[str, int], jarvis: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        """The map dots: one per located address, with its connection count."""
        out = []
        for ip, n in ips.items():
            place = self.places.get(ip, {})
            if "lat" in place:
                dot = {"ip": ip, "n": n, **place}
                if jarvis is not None:
                    dot["j"] = jarvis.get(ip, 0)
                out.append(dot)
        return out

    def step(self) -> None:
        """Refresh the connection list for the map."""
        output = subprocess.check_output(  # nosec B603 - fixed program and arguments
            [program("netstat"), "-n", "-o", "-p", "tcp"], text=True, timeout=8
        )
        ips = public_ips(output)
        self.look_up([i for i in ips if i not in self.places])
        mine = jarvis_pids()
        jn: dict[str, int] = {}
        for ip, pid in public_conns(output):
            if pid in mine:
                jn[ip] = jn.get(ip, 0) + 1
        live.set("conns", self.map_dots(ips, jn))


def start() -> None:
    """Start the connection loop in the background."""
    cache = GeoCache()
    threading.Thread(target=every(CONN_EVERY, cache.step), daemon=True).start()
