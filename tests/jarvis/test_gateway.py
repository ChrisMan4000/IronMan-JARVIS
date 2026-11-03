"""Remote-access gateway: password, session cookie, lockout, public paths, routing."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
from starlette.testclient import TestClient  # noqa: E402

TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
if TOOLS not in sys.path:
    sys.path.append(TOOLS)

import gateway  # noqa: E402

PASSWORD = "correct horse"


@pytest.fixture
def gw(tmp_path, monkeypatch):
    auth_file = tmp_path / "auth.json"
    monkeypatch.setattr(gateway, "AUTH_FILE", auth_file)
    monkeypatch.setattr(gateway, "PBKDF2_ITERATIONS", 1000)  # keep the tests fast
    auth_file.write_text(json.dumps(gateway.new_auth(PASSWORD)), encoding="utf-8")
    gateway.lockout.clear()
    with TestClient(gateway.app, base_url="https://testserver") as client:
        yield client


def test_password_check():
    auth = gateway.new_auth("secret1")
    assert gateway.password_matches(auth, "secret1")
    assert not gateway.password_matches(auth, "secret2")
    assert not gateway.password_matches(None, "secret1")


def test_cookie_is_signed_and_expires(monkeypatch):
    auth = gateway.new_auth("x")
    cookie = gateway.make_cookie(auth)
    assert gateway.cookie_valid(auth, cookie)
    assert not gateway.cookie_valid(
        gateway.new_auth("x"), cookie
    )  # new password: old logins invalid
    expires, sig = cookie.split(".")
    assert not gateway.cookie_valid(
        auth, "%d.%s" % (int(expires) + 999, sig)
    )  # tampered expiry
    assert not gateway.cookie_valid(auth, "garbage")
    monkeypatch.setattr(gateway.time, "time", lambda: int(expires) + 1)
    assert not gateway.cookie_valid(auth, cookie)


def test_lockout_after_five_wrong_tries(monkeypatch):
    gateway.lockout.clear()
    for _ in range(gateway.MAX_TRIES - 1):
        gateway.record_failure("10.0.0.7")
    assert not gateway.locked_out("10.0.0.7")
    gateway.record_failure("10.0.0.7")
    assert gateway.locked_out("10.0.0.7") and not gateway.locked_out("10.0.0.8")
    now = time.time()
    monkeypatch.setattr(gateway.time, "time", lambda: now + gateway.LOCKOUT_SECONDS + 1)
    assert not gateway.locked_out("10.0.0.7")


def test_login_flow(gw):
    assert gw.get("/login").status_code == 200
    wrong = gw.post("/login", data={"pw": "nope"}, follow_redirects=False)
    assert wrong.status_code == 401 and "Wrong password." in wrong.text
    ok = gw.post("/login", data={"pw": PASSWORD}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/hud.html"
    assert gateway.COOKIE in ok.cookies


def test_login_is_refused_while_locked_out(gw):
    for _ in range(gateway.MAX_TRIES):
        gw.post("/login", data={"pw": "nope"})
    locked = gw.post("/login", data={"pw": PASSWORD}, follow_redirects=False)
    assert locked.status_code == 429  # even the right password waits


def test_everything_else_needs_a_login(gw):
    page = gw.get("/hud.html", headers={"accept": "text/html"}, follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/login"
    assert gw.get("/helper/").status_code == 401
    assert gw.post("/v1/chat/completions", json={}).status_code == 401


def test_public_icons_skip_the_login(gw):
    # A public path gets past the login check: 502 when no HUD web server runs, 200 when
    # Jarvis is running on this PC (never 401 or a redirect to the login page).
    assert gw.get("/hud.webmanifest", follow_redirects=False).status_code in (200, 502)
    assert gw.post("/hud.webmanifest").status_code == 401  # only GET/HEAD are public


@pytest.mark.parametrize(
    "path, base, backend_path",
    [
        ("/helper/m/list", "http://127.0.0.1:8765", "/m/list"),
        ("/helper", "http://127.0.0.1:8765", "/"),
        ("/wake", "http://127.0.0.1:8766", "/"),
        ("/v1/chat/completions", "http://127.0.0.1:8000", "/v1/chat/completions"),
        ("/api/tools", "http://127.0.0.1:8000", "/api/tools"),
        ("/hud.html", "http://localhost:5173", "/hud.html"),
        ("/helperx", "http://localhost:5173", "/helperx"),
    ],
)
def test_backend_for(path, base, backend_path):
    assert gateway.backend_for(path)[:2] == (base, backend_path)


def test_helper_gets_the_hud_origin_and_no_cookie():
    _base, _path, forced = gateway.backend_for("/helper/hue")
    hdrs = gateway.forwarded_headers(
        {
            "cookie": "jarvis_gw=1.x",
            "origin": "https://evil.example",
            "connection": "close",
            "accept": "*/*",
        },
        forced,
    )
    assert hdrs == {
        "accept": "*/*",
        "host": "127.0.0.1:8765",
        "origin": "http://localhost:5173",
    }
