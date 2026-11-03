"""Live numbers for the HUD (GET / of the helper): CPU, network, GPU, fans, connections,
loaded model, CO2, tool lights and the benchmark result.

Each value is refreshed by its own background loop, started by start(). A loop that
hits an error keeps running and reports "no value" (None) until the source answers.
"""

from __future__ import annotations

import ctypes
import ipaddress
import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

logger = logging.getLogger(__name__)

LINK_MBPS = 250  # your DSL line speed (250 Mbps)
JARVIS_DIR = os.path.join(os.path.expanduser("~"), ".openjarvis")
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: no console flashes when calling lms
LMSTUDIO_MODELS_URL = "http://localhost:1234/api/v0/models"
FANS_URL = (
    "http://127.0.0.1:8085/data.json"  # LibreHardwareMonitor web server (read-only)
)
CO2_URLS = (
    "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_weekly_mlo.txt",
    "https://gml.noaa.gov/aftp/products/trends/co2/co2_weekly_mlo.txt",
)
GPU_QUERY = (
    "name,utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw,fan.speed"
)
GEO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dbip.mmdb")

# Shared data returned by GET /
stats: dict[str, Any] = {
    "co2": None,
    "model": None,
    "model_gb": None,
    "conns": [],
    "cpu_load": 0,
    "cpu_temp": None,
    "gpu": None,
    "net": {
        "down_pct": 0,
        "up_pct": 0,
        "down_mbps": 0,
        "up_mbps": 0,
        "link_mbps": LINK_MBPS,
    },
}


# -------------------------------------------------------------- CPU / network / GPU
class FileTime(ctypes.Structure):
    """Windows FILETIME: a 64-bit count of 100 ns ticks split in two halves."""

    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

    def ticks(self) -> int:
        return (self.hi << 32) | self.lo


def cpu_times() -> tuple[int, int]:
    """(idle, total) CPU time from Windows."""
    idle, kernel, user = FileTime(), FileTime(), FileTime()
    ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    return idle.ticks(), kernel.ticks() + user.ticks()


def net_bytes() -> tuple[int, int] | None:
    """(received, sent) bytes since boot, read from 'netstat -e'."""
    out = subprocess.check_output(["netstat", "-e"], text=True, timeout=5)
    for line in out.splitlines():
        m = re.match(r"^\s*\S+\s+(\d+)\s+(\d+)\s*$", line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def net_speed(
    before: tuple[int, int], after: tuple[int, int], seconds: float
) -> dict[str, float]:
    """Download/upload in Mbit/s and as a share of the line speed."""
    dt = max(0.1, seconds)
    down = max(0, after[0] - before[0]) * 8 / dt / 1e6
    up = max(0, after[1] - before[1]) * 8 / dt / 1e6
    return {
        "down_pct": round(min(100, 100 * down / LINK_MBPS), 2),
        "up_pct": round(min(100, 100 * up / LINK_MBPS), 2),
        "down_mbps": round(down, 2),
        "up_mbps": round(up, 2),
        "link_mbps": LINK_MBPS,
    }


def parse_gpu(line: str) -> dict[str, Any]:
    """One CSV line of nvidia-smi (GPU_QUERY order) -> the HUD's gpu values."""
    name, load, temp, mem_used, mem_total, power, fan = [
        s.strip() for s in line.split(",")
    ]
    return {
        "name": name,
        "load": float(load),
        "temp": float(temp),
        "mem_used": float(mem_used),
        "mem_total": float(mem_total),
        "power": float(power),
        "fan": float(fan) if fan[:1].isdigit() else None,
    }


def read_gpu() -> dict[str, Any] | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=" + GPU_QUERY, "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        )
        return parse_gpu(out.strip())
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ):  # no NVIDIA GPU or driver busy
        return None


def sampler() -> None:
    """Once per second: CPU load, network speed and GPU values (nvidia-smi)."""
    prev_cpu: tuple[int, int] | None = None
    prev_net: tuple[int, int] | None = None
    prev_t = time.time()
    while True:
        try:
            cur = cpu_times()
            if prev_cpu:
                idle, total = cur[0] - prev_cpu[0], cur[1] - prev_cpu[1]
                if total > 0:
                    stats["cpu_load"] = round(100 * (1 - idle / total), 1)
            prev_cpu = cur
        except (OSError, AttributeError) as exc:  # not Windows, or the call failed once
            logger.debug("cpu sample failed: %s", exc)
        try:
            now_net, now_t = net_bytes(), time.time()
            if now_net and prev_net:
                stats["net"] = net_speed(prev_net, now_net, now_t - prev_t)
            prev_net, prev_t = now_net, now_t
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("network sample failed: %s", exc)
        stats["gpu"] = read_gpu()
        time.sleep(1)


# ---------------------------------------------------------- connections (world map)
geo: dict[str, dict[str, Any]] = {}
_geo_reader: Any = None


def open_geo_db() -> None:
    """Open the offline location database (no data leaves this PC); none = no dots."""
    global _geo_reader
    try:
        import maxminddb

        _geo_reader = maxminddb.open_database(GEO_DB)
    except (ImportError, OSError, ValueError) as exc:
        logger.debug("no location database: %s", exc)
        _geo_reader = None


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


def geo_lookup(ips: list[str]) -> None:
    for ip in ips:
        try:
            geo[ip] = locate(_geo_reader.get(ip) if _geo_reader else None)
        except ValueError:  # not an address the database understands
            geo[ip] = {"bad": 1}


def connections_snapshot(ips: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "ip": i,
            "n": n,
            "lat": geo[i]["lat"],
            "lon": geo[i]["lon"],
            "country": geo[i].get("country", ""),
            "city": geo[i].get("city", ""),
            "org": geo[i].get("org", ""),
        }
        for i, n in ips.items()
        if i in geo and "lat" in geo[i]
    ]


def conn_step() -> None:
    """Refresh the connection list for the map."""
    ips = public_ips(
        subprocess.check_output(["netstat", "-n", "-p", "tcp"], text=True, timeout=8)
    )
    new = [i for i in ips if i not in geo]
    if new:
        geo_lookup(new)
    stats["conns"] = connections_snapshot(ips)


# --------------------------------------------------------- loaded model (LM Studio)
_size_cache: dict[str, Any] = {"id": None, "gb": None, "t": 0.0}


def model_size_gb(mid: str | None) -> float | None:
    """Size of the loaded model in GB from 'lms ps --json' (cached per model)."""
    if not mid:
        return None
    if _size_cache["id"] == mid and (
        _size_cache["gb"] is not None or time.time() - _size_cache["t"] < 30
    ):
        return _size_cache["gb"]
    _size_cache.update(id=mid, t=time.time(), gb=None)
    try:
        out = subprocess.run(
            ["lms", "ps", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=NO_WINDOW,
        ).stdout
        for m in json.loads(out):
            if m.get("identifier") == mid or m.get("modelKey") == mid:
                _size_cache["gb"] = round(m["sizeBytes"] / 1e9, 1)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        logger.debug("lms ps failed: %s", exc)
    return _size_cache["gb"]


def loaded_llm(models: list[dict[str, Any]]) -> str | None:
    loaded = [
        m["id"]
        for m in models
        if m.get("state") == "loaded" and m.get("type") in ("llm", "vlm")
    ]
    return loaded[0] if loaded else None


def model_step() -> None:
    """Which LLM is loaded in LM Studio, and its size."""
    try:
        with urllib.request.urlopen(LMSTUDIO_MODELS_URL, timeout=4) as r:  # nosec B310 - fixed local URL
            stats["model"] = loaded_llm(json.load(r).get("data", []))
    except (OSError, ValueError):  # LM Studio not running
        stats["model"] = None
    stats["model_gb"] = model_size_gb(stats["model"])


# ----------------------------------------------------------------- CO2 value (NOAA)
def latest_co2(text: str) -> dict[str, Any] | None:
    """Last valid weekly value of NOAA's Mauna Loa file: {"ppm", "date"}."""
    last = None
    for line in text.splitlines():
        p = line.split()
        if line.startswith("#") or len(p) < 5:
            continue
        try:
            ppm = float(p[4])
            date = "%s-%02d-%02d" % (p[0], int(p[1]), int(p[2]))
        except ValueError:
            continue
        if ppm > 0:  # -999.99 marks a missing week
            last = {"ppm": ppm, "date": date}
    return last


def co2_loop() -> None:
    """Latest weekly CO2 value from NOAA Mauna Loa, refreshed every 6 hours."""
    while True:
        value = None
        for url in CO2_URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "jarvis-hud"})
                with urllib.request.urlopen(req, timeout=15) as r:  # nosec B310 - fixed NOAA https URLs
                    value = latest_co2(r.read().decode())
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("co2 download failed: %s", exc)
            if value:
                stats["co2"] = value
                break
        time.sleep(6 * 3600 if value else 600)


# --------------------------------------------------------------- small file readers
def _read_number(path: str) -> float:
    try:
        with open(path, encoding="utf-8") as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return 0.0


def tools_step() -> None:
    """When web_search / oracle_search last ran (for the two HUD lights)."""
    stats["tools"] = {
        "now": time.time(),
        "web": _read_number(os.path.join(JARVIS_DIR, "tool-web_search.txt")),
        "doc": _read_number(os.path.join(JARVIS_DIR, "tool-oracle_search.txt")),
    }


def bench_step() -> None:
    """The last benchmark result (written by tools\\bench.py)."""
    try:
        with open(os.path.join(JARVIS_DIR, "bench-result.json"), encoding="utf-8") as f:
            d = json.load(f)
        stats["bench"] = {k: d.get(k) for k in ("accuracy", "passed", "total", "time")}
    except (OSError, ValueError):
        stats["bench"] = None


def fan_speeds(
    node: dict[str, Any], out: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Every "... RPM" sensor in LibreHardwareMonitor's tree (GPU fans are left out)."""
    out = [] if out is None else out
    value = str(node.get("Value", ""))
    if value.endswith("RPM"):
        m = re.match(r"[\d.,]+", value)
        name = str(node.get("Text", ""))[:40]
        if m and not name.startswith("GPU Fan"):
            out.append({"name": name, "rpm": int(float(m.group(0).replace(",", ".")))})
    for child in node.get("Children", []) or []:
        fan_speeds(child, out)
    return out


def fans_step() -> None:
    try:
        with urllib.request.urlopen(FANS_URL, timeout=3) as r:  # nosec B310 - fixed local URL
            stats["fans"] = fan_speeds(json.loads(r.read().decode("utf-8")))
    except (OSError, ValueError):  # LibreHardwareMonitor not running
        stats["fans"] = None


# ---------------------------------------------------------------------------- loops
def every(seconds: float, step: Callable[[], None]) -> Callable[[], None]:
    """Loop: run step, then wait; an unexpected error is logged once, never fatal."""

    def loop() -> None:
        reported = False
        while True:
            try:
                step()
                reported = False
            except Exception:  # keep the HUD value loop alive whatever one source does
                if not reported:
                    logger.exception(
                        "%s failed (logged once until it works again)", step.__name__
                    )
                    reported = True
            time.sleep(seconds)

    return loop


def start() -> None:
    """Start every sampling loop in the background."""
    open_geo_db()
    loops = [
        sampler,
        every(5, conn_step),
        every(3, model_step),
        co2_loop,
        every(1, tools_step),
        every(2, fans_step),
        every(10, bench_step),
    ]
    for loop in loops:
        threading.Thread(target=loop, daemon=True).start()
