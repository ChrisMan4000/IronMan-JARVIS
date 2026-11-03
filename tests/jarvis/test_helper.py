"""The HUD helper (tools/hwstats.py + helper_* modules): security, parsing, routing."""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
if TOOLS not in sys.path:
    sys.path.append(TOOLS)

import helper_docs  # noqa: E402
import helper_geo  # noqa: E402
import helper_http  # noqa: E402
import helper_models  # noqa: E402
import helper_stats  # noqa: E402
import hwstats  # noqa: E402

HUD = "http://localhost:5173"


class FakeRequest:
    """Just enough of BaseHTTPRequestHandler for the helper functions."""

    def __init__(self, path="/", host="127.0.0.1:8765", origin=None, referer=None):
        self.path = path
        self.headers = {"Host": host}
        if origin:
            self.headers["Origin"] = origin
        if referer:
            self.headers["Referer"] = referer
        self.wfile = io.BytesIO()
        self.code = None
        self.sent_headers = {}

    def send_response(self, code):
        self.code = code

    def send_header(self, k, v):
        self.sent_headers[k] = v

    def end_headers(self):
        pass

    def json(self):
        return json.loads(self.wfile.getvalue())


# ---------------------------------------------------------------------- helper_http
@pytest.mark.parametrize(
    "host, ok",
    [
        ("127.0.0.1:8765", True),
        ("LOCALHOST:8765", True),
        ("evil.example:8765", False),
        ("127.0.0.1", False),
    ],
)
def test_host_check_stops_dns_rebinding(host, ok):
    assert helper_http.host_ok(FakeRequest(host=host)) is ok


@pytest.mark.parametrize(
    "origin, referer, trusted",
    [
        (HUD, None, HUD),
        ("http://evil.example", HUD + "/", None),  # an Origin header always wins
        (None, HUD + "/hud.html", HUD),
        (None, HUD, HUD),
        (None, "http://localhost:51730/", None),  # same prefix, different port
        (None, None, None),
    ],
)
def test_trusted_origin(origin, referer, trusted):
    assert (
        helper_http.trusted_origin(FakeRequest(origin=origin, referer=referer))
        == trusted
    )


def test_cors_header_only_for_the_hud():
    h = FakeRequest(origin=HUD)
    helper_http.send(h, 200, {"a": 1})
    assert h.sent_headers["Access-Control-Allow-Origin"] == HUD and h.json() == {"a": 1}
    other = FakeRequest(origin="http://evil.example")
    helper_http.send(other, 200, {"a": 1})
    assert "Access-Control-Allow-Origin" not in other.sent_headers


def test_tool_route_refuses_other_sites_and_wraps_results():
    calls = []
    route = helper_http.trusted_tool_route(
        "hue", lambda q: calls.append(q) or SimpleNamespace(success=True, content="ok")
    )
    refused = FakeRequest("/hue?room=kitchen", origin="http://evil.example")
    route(refused)
    assert refused.code == 403 and calls == []
    allowed = FakeRequest("/hue?room=kitchen&state=on", origin=HUD)
    route(allowed)
    assert allowed.json() == {"ok": True, "text": "ok"} and calls == [
        {"room": "kitchen", "state": "on"}
    ]


def test_tool_reply_hides_crashes_and_passes_refusals():
    def boom():
        raise RuntimeError("secret detail")

    assert helper_http.tool_reply("tado", boom) == {
        "ok": False,
        "text": "tado error: RuntimeError",
    }
    refusal = {"ok": False, "text": "refused"}
    assert helper_http.tool_reply("tado", lambda: refusal) is refusal
    long = helper_http.tool_reply(
        "search", lambda: SimpleNamespace(success=True, content="x" * 50), max_chars=10
    )
    assert long["text"] == "x" * 10


# --------------------------------------------------------------------- helper_stats
def test_net_speed():
    speed = helper_stats.net_speed((0, 0), (31_250_000, 3_125_000), 1.0)
    assert (
        speed["down_mbps"] == 250.0
        and speed["down_pct"] == 100
        and speed["up_mbps"] == 25.0
    )


def test_parse_gpu():
    gpu = helper_stats.parse_gpu(
        "NVIDIA GeForce RTX 5090, 37, 61, 9000, 32607, 120.5, [N/A]"
    )
    assert (
        gpu["name"] == "NVIDIA GeForce RTX 5090"
        and gpu["load"] == 37
        and gpu["fan"] is None
    )


def test_public_ips_skips_local_addresses():
    netstat = """
  TCP    192.168.2.20:51000     140.82.112.4:443       ESTABLISHED
  TCP    192.168.2.20:51001     140.82.112.4:443       ESTABLISHED
  TCP    192.168.2.20:51002     192.168.2.101:80       ESTABLISHED
  TCP    127.0.0.1:8765         127.0.0.1:51003        ESTABLISHED
  TCP    [::1]:5173             [::1]:51004            ESTABLISHED
  TCP    192.168.2.20:51005     151.101.1.69:443       TIME_WAIT
"""
    assert helper_geo.public_ips(netstat) == {"140.82.112.4": 2}


def test_locate():
    rec = {
        "location": {"latitude": 52.5, "longitude": 13.4},
        "country": {"names": {"en": "Germany"}},
    }
    assert helper_geo.locate(rec) == {
        "lat": 52.5,
        "lon": 13.4,
        "country": "Germany",
        "city": "",
        "org": "",
    }
    assert helper_geo.locate(None) == {"bad": 1}


def test_latest_co2_skips_missing_weeks():
    text = (
        "# header\n2026 10 18 2026.79 424.10 7\n"
        "2026 10 25 2026.81 -999.99 0\nshort line\n"
    )
    assert helper_stats.latest_co2(text) == {"ppm": 424.10, "date": "2026-10-18"}
    assert helper_stats.latest_co2("# only comments\n") is None


def test_fan_speeds_leaves_out_gpu_fans():
    tree = {
        "Text": "PC",
        "Children": [
            {"Text": "Fan #1", "Value": "1234 RPM"},
            {"Text": "GPU Fan 1", "Value": "900 RPM"},
            {
                "Text": "CPU",
                "Value": "45 °C",
                "Children": [{"Text": "Pump", "Value": "2100 RPM"}],
            },
        ],
    }
    assert helper_stats.fan_speeds(tree) == [
        {"name": "Fan #1", "rpm": 1234},
        {"name": "Pump", "rpm": 2100},
    ]


def test_loop_survives_errors(monkeypatch):
    runs = []

    def flaky():
        runs.append(1)
        if len(runs) < 3:
            raise RuntimeError("source not ready")
        raise SystemExit  # stop the test loop

    monkeypatch.setattr(helper_stats.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit):
        helper_stats.every(1, flaky)()
    assert len(runs) == 3


def test_loaded_llm_ignores_embedding_models():
    models = [
        {"id": "nomic", "state": "loaded", "type": "embeddings"},
        {"id": "gemma", "state": "loaded", "type": "llm"},
    ]
    assert helper_stats.loaded_llm(models) == "gemma"
    assert helper_stats.loaded_llm([]) is None


# -------------------------------------------------------------------- helper_models
def test_settings_from_query_clamps_context():
    assert helper_models.settings_from_query(
        {"reasoning": "1", "thinking": "0", "context": "99999999"}
    ) == {
        "reasoning": True,
        "thinking": False,
        "context": helper_models.CONTEXT_RANGE[1],
    }
    assert helper_models.settings_from_query({"context": "10"}) == {"context": 1024}


def test_settings_are_saved_per_model(tmp_path, monkeypatch):
    monkeypatch.setattr(helper_models, "SETTINGS_PATH", str(tmp_path / "s.json"))
    helper_models.put_setting("gemma", context=65536)
    assert helper_models.get_setting("gemma") == {
        "reasoning": False,
        "thinking": False,
        "context": 65536,
    }
    assert helper_models.get_setting("other") == helper_models.SET_DEFAULTS


def test_switch_matters():
    assert helper_models.switch_matters((10, False), (10, True))
    assert helper_models.switch_matters((10, False), (40, False))
    assert not helper_models.switch_matters((10, False), (12, False))


def test_only_one_model_load_at_a_time(monkeypatch, tmp_path):
    monkeypatch.setattr(helper_models, "SETTINGS_PATH", str(tmp_path / "s.json"))
    started, release = [], threading.Event()

    def slow_load(mid, ctx):
        started.append(mid)
        release.wait(2)
        helper_models.work.loading = None

    monkeypatch.setattr(helper_models, "_do_load", slow_load)
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(helper_models.start_load("gemma"))
        )
        for _ in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    release.set()
    time.sleep(0.05)
    assert started == ["gemma"]
    assert sum(1 for r in results if r.get("error") == "busy") == 4


# ---------------------------------------------------------------------- helper_docs
@pytest.fixture
def oracle(tmp_path, monkeypatch):
    root = tmp_path / "ORACLE"
    (root / "climate").mkdir(parents=True)
    (root / "climate" / "IPCC Report 2026.pdf").write_bytes(b"%PDF")
    (root / "notes.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    try:
        os.symlink(secret, root / "link.txt")
    except OSError:
        pass
    monkeypatch.setattr(helper_docs, "DOC_ROOT", str(root))
    helper_docs.doc_index.forget()
    return root


def test_find_doc(oracle):
    assert helper_docs.find_doc("ipcc report 2026.pdf").endswith("IPCC Report 2026.pdf")
    assert helper_docs.find_doc("IPCC").endswith(
        "IPCC Report 2026.pdf"
    )  # unique partial name
    assert helper_docs.find_doc("") is None
    assert helper_docs.find_doc("missing.pdf") is None


def test_links_out_of_the_folder_are_not_served(oracle):
    if not (oracle / "link.txt").is_symlink():
        pytest.skip("symlinks not available")
    assert helper_docs.find_doc("link.txt") is None


def test_script_files_are_sent_as_plain_text(oracle):
    h = FakeRequest("/doc?f=notes.html")
    helper_docs.serve_doc(h)
    assert (
        h.code == 200 and h.sent_headers["Content-Type"] == "text/plain; charset=utf-8"
    )


# -------------------------------------------------------------------------- routing
def _get(path, **headers):
    h = FakeRequest(path, **headers)
    h.routes = hwstats.HelperHandler.routes
    hwstats.HelperHandler.do_GET(h)
    return h


def test_routing(monkeypatch):
    monkeypatch.setattr(
        hwstats.HelperHandler,
        "routes",
        {
            **hwstats.ROUTES,
            "/home/state": lambda h: helper_http.send(h, 200, {"home": 1}),
        },
    )
    assert _get("/", host="evil.example:8765").code == 403
    assert _get("/nothing").code == 404
    assert _get("/home/state").json() == {"home": 1}
    assert _get("/hue?room=x&state=on").code == 403  # not from the HUD
    assert "cpu_load" in _get("/").json()


def test_news_limit():
    assert [hwstats.news_limit(v) for v in ("3", "0", "99", "x")] == [3, 1, 10, 5]


def test_private_routes_old_and_new_style(monkeypatch):
    monkeypatch.setattr(hwstats, "hwstats_private", None)  # no private file
    assert hwstats.private_routes() == {}
    monkeypatch.setattr(
        hwstats, "hwstats_private", SimpleNamespace(routes=lambda: {"/a": 1})
    )
    assert hwstats.private_routes() == {"/a": 1}
    seen = {}
    monkeypatch.setattr(
        hwstats,
        "hwstats_private",
        SimpleNamespace(setup=lambda g: seen.update(g) or {"/b": 2}),
    )
    assert hwstats.private_routes() == {"/b": 2} and sorted(seen) == [
        "need_trusted",
        "query",
        "send",
    ]
