"""Local HTTPS + password gateway for the Jarvis HUD (local version only).

Listens on 0.0.0.0:8443 (HTTPS, mkcert certificate) and forwards, after a
password login, to the services that stay on 127.0.0.1:
  /helper/*  -> helper   127.0.0.1:8765  (path prefix removed)
  /wake      -> wake     127.0.0.1:8766
  /v1 /health /api -> Jarvis server 8000
  everything else  -> Vite 5173 (page and hud.html)
The gateway is the trust boundary: it sets the Host / Origin headers the helper
expects. Set the password with:  python tools\\gateway.py --set-password
Files (never share them): %USERPROFILE%\\.openjarvis\\gateway\\{cert,key}.pem, auth.json
"""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Route

GATEWAY_DIR = Path(
    os.environ.get("JARVIS_GATEWAY_DIR") or (Path.home() / ".openjarvis" / "gateway")
)
AUTH_FILE = GATEWAY_DIR / "auth.json"
COOKIE = "jarvis_gw"
SESSION_SECONDS = 30 * 24 * 3600
PBKDF2_ITERATIONS = 200000
MIN_PASSWORD = 4
MAX_TRIES = 5  # wrong passwords in a row before a lockout
LOCKOUT_SECONDS = 300
# Headers that belong to one connection and must not be passed on by a proxy.
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}
# Home Screen icons and the web app manifest: the iPhone fetches them without a login.
PUBLIC_PATHS = {
    "/jarvis-icon-180.png",
    "/jarvis-icon-192.png",
    "/jarvis-icon-512.png",
    "/hud.webmanifest",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/favicon.ico",
}

_failed_logins: dict[str, list[float]] = {}  # ip -> [wrong tries, locked until]
_client: httpx.AsyncClient | None = None


# ------------------------------------------------------------------------- password
def load_auth() -> dict | None:
    try:
        return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # no password set yet, or a damaged file
        return None


def hash_password(pw: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, PBKDF2_ITERATIONS)


def password_matches(auth: dict | None, pw: str) -> bool:
    if not auth:
        return False
    return hmac.compare_digest(
        hash_password(pw, bytes.fromhex(auth["salt"])).hex(), auth["hash"]
    )


def new_auth(pw: str) -> dict:
    """Salt, password hash and a fresh cookie secret (so old logins stop working)."""
    salt = os.urandom(16)
    return {
        "salt": salt.hex(),
        "hash": hash_password(pw, salt).hex(),
        "secret": secrets.token_hex(32),
    }


def set_password() -> int:
    import getpass

    p1 = getpass.getpass(
        "New gateway password (at least %d characters): " % MIN_PASSWORD
    )
    p2 = getpass.getpass("Repeat it: ")
    if p1 != p2:
        print("The two entries differ. Nothing saved.")
        return 1
    if len(p1) < MIN_PASSWORD:
        print("Too short (minimum %d). Nothing saved." % MIN_PASSWORD)
        return 1
    GATEWAY_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(new_auth(p1)), encoding="utf-8")
    print("Password saved. All old logins are now invalid.")
    return 0


# ------------------------------------------------------------------- session cookie
def sign(secret: str, expires: object) -> str:
    return hmac.new(
        bytes.fromhex(secret), str(expires).encode(), hashlib.sha256
    ).hexdigest()


def make_cookie(auth: dict) -> str:
    """Cookie "<expiry>.<signature>": only valid until expiry, with this secret."""
    expires = int(time.time()) + SESSION_SECONDS
    return f"{expires}.{sign(auth['secret'], expires)}"


def cookie_valid(auth: dict | None, cookie: str) -> bool:
    if not auth or "." not in cookie:
        return False
    expires, signature = cookie.split(".", 1)
    try:
        if int(expires) < time.time():
            return False
    except ValueError:
        return False
    return hmac.compare_digest(signature, sign(auth["secret"], expires))


def authed(request) -> bool:
    return cookie_valid(load_auth(), request.cookies.get(COOKIE, ""))


# -------------------------------------------------------------------------- lockout
def locked_out(ip: str) -> bool:
    return _failed_logins.get(ip, [0, 0])[1] > time.time()


def record_failure(ip: str) -> None:
    """Count a wrong password; the MAX_TRIES-th one locks the address for a while."""
    tries = _failed_logins.get(ip, [0, 0])[0] + 1
    _failed_logins[ip] = (
        [0, time.time() + LOCKOUT_SECONDS] if tries >= MAX_TRIES else [tries, 0]
    )


def record_success(ip: str) -> None:
    _failed_logins.pop(ip, None)


# ---------------------------------------------------------------------------- pages
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>J.A.R.V.I.S.</title><style>
body{margin:0;background:#050b12;color:#19d3ff;font-family:Consolas,monospace;display:flex;
align-items:center;justify-content:center;min-height:100vh}
form{border:1px solid #19d3ff55;padding:28px;width:min(86vw,320px);background:#0a1620}
h1{font-size:18px;letter-spacing:6px;margin:0 0 18px;text-align:center}
input{width:100%;box-sizing:border-box;padding:12px;background:#050b12;color:#19d3ff;
border:1px solid #19d3ff55;font-size:16px;margin-bottom:12px}
button{width:100%;padding:12px;background:#19d3ff22;color:#19d3ff;border:1px solid #19d3ff;
font-size:16px;letter-spacing:3px}
p{color:#ff9a3d;font-size:13px;text-align:center;margin:0 0 12px}
</style></head><body><form method="post" action="/login">
<h1>J.A.R.V.I.S.</h1>%MSG%
<input type="password" name="pw" placeholder="password" autofocus autocomplete="current-password">
<button type="submit">ENTER</button></form></body></html>"""


def login_page(message: str = "", status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        PAGE.replace("%MSG%", "<p>%s</p>" % message if message else ""),
        status_code=status,
    )


async def login(request):
    ip = request.client.host if request.client else "?"
    if request.method == "GET":
        return login_page()
    if locked_out(ip):
        return login_page("Too many tries. Wait 5 minutes.", 429)
    form = parse_qs((await request.body()).decode("utf-8", "ignore"))
    auth = load_auth()
    if not password_matches(auth, (form.get("pw") or [""])[0]):
        record_failure(ip)
        return login_page("Wrong password.", 401)
    record_success(ip)
    resp = RedirectResponse("/hud.html", status_code=303)
    resp.set_cookie(
        COOKIE,
        make_cookie(auth),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


async def logout(request):
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


# ----------------------------------------------------------------------- forwarding
def backend_for(path: str) -> tuple[str, str, dict[str, str]]:
    """(backend base url, path at the backend, headers the backend must see)."""
    if path == "/helper" or path.startswith("/helper/"):
        return (
            "http://127.0.0.1:8765",
            path[len("/helper") :] or "/",
            {"host": "127.0.0.1:8765", "origin": "http://localhost:5173"},
        )
    if path == "/wake" or path.startswith("/wake/"):
        return (
            "http://127.0.0.1:8766",
            path[len("/wake") :] or "/",
            {"host": "127.0.0.1:8766"},
        )
    if path.startswith("/v1") or path == "/health" or path.startswith("/api/"):
        return "http://127.0.0.1:8000", path, {"host": "localhost:8000"}
    return "http://localhost:5173", path, {"host": "localhost:5173"}


def forwarded_headers(
    incoming: dict[str, str], forced: dict[str, str]
) -> dict[str, str]:
    """Backend headers: no hop-by-hop headers, login cookie or browser origin."""
    hdrs = {
        k: v
        for k, v in incoming.items()
        if k not in HOP_BY_HOP_HEADERS and k not in ("cookie", "origin", "referer")
    }
    hdrs.update(forced)
    return hdrs


async def proxy(request):
    public = request.method in ("GET", "HEAD") and request.url.path in PUBLIC_PATHS
    path = (
        "/jarvis-icon-180.png"
        if request.url.path.startswith("/apple-touch-icon")
        else request.url.path
    )
    if not public and not authed(request):
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return Response("login required", status_code=401)
    base, backend_path, forced = backend_for(path)
    url = base + backend_path + (("?" + request.url.query) if request.url.query else "")
    body = None if request.method in ("GET", "HEAD") else request.stream()
    try:
        req = _client.build_request(
            request.method,
            url,
            headers=forwarded_headers(dict(request.headers), forced),
            content=body,
        )
        r = await _client.send(req, stream=True)
    except httpx.HTTPError as e:
        return Response("backend not reachable: " + type(e).__name__, status_code=502)
    out = {k: v for k, v in r.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}
    out["x-content-type-options"] = "nosniff"
    out["referrer-policy"] = "no-referrer"
    return StreamingResponse(
        r.aiter_raw(),
        status_code=r.status_code,
        headers=out,
        background=BackgroundTask(r.aclose),
    )


@asynccontextmanager
async def lifespan(app):
    global _client
    _client = httpx.AsyncClient(
        timeout=httpx.Timeout(900.0, connect=5.0),
        limits=httpx.Limits(max_connections=100),
    )
    yield
    await _client.aclose()


app = Starlette(
    routes=[
        Route("/login", login, methods=["GET", "POST"]),
        Route("/logout", logout, methods=["GET"]),
        Route(
            "/{path:path}",
            proxy,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        ),
    ],
    lifespan=lifespan,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set-password", action="store_true")
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--no-tls", action="store_true", help="test only")
    args = ap.parse_args()
    if args.set_password:
        sys.exit(set_password())
    if not load_auth():
        print("No password set. Run:  python tools\\gateway.py --set-password")
        sys.exit(1)
    tls = (
        {}
        if args.no_tls
        else {
            "ssl_certfile": str(GATEWAY_DIR / "cert.pem"),
            "ssl_keyfile": str(GATEWAY_DIR / "key.pem"),
        }
    )
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning", **tls)  # nosec B104 - LAN access is the point


if __name__ == "__main__":
    main()
