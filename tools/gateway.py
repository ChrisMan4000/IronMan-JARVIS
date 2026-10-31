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
import os
import secrets
import sys
import time
import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route

GDIR = Path(os.environ.get("JARVIS_GATEWAY_DIR") or (Path.home() / ".openjarvis" / "gateway"))
AUTH = GDIR / "auth.json"
COOKIE = "jarvis_gw"
SESSION_SECONDS = 30 * 24 * 3600
ITER = 200000
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
       "trailers", "transfer-encoding", "upgrade", "host"}
FAILS = {}  # ip -> [count, locked_until]
CLIENT = None


def load_auth():
    try:
        return json.loads(AUTH.read_text(encoding="utf-8"))
    except Exception:
        return None


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ITER)


def set_password():
    import getpass
    p1 = getpass.getpass("New gateway password (at least 4 characters): ")
    p2 = getpass.getpass("Repeat it: ")
    if p1 != p2:
        print("The two entries differ. Nothing saved.")
        return 1
    if len(p1) < 4:
        print("Too short (minimum 4). Nothing saved.")
        return 1
    GDIR.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(16)
    data = {"salt": salt.hex(), "hash": hash_pw(p1, salt).hex(), "secret": secrets.token_hex(32)}
    AUTH.write_text(json.dumps(data), encoding="utf-8")
    print("Password saved. All old logins are now invalid.")
    return 0


def sign(secret, exp):
    return hmac.new(bytes.fromhex(secret), str(exp).encode(), hashlib.sha256).hexdigest()


def make_cookie(auth):
    exp = int(time.time()) + SESSION_SECONDS
    return f"{exp}.{sign(auth['secret'], exp)}"


def authed(request):
    auth = load_auth()
    c = request.cookies.get(COOKIE, "")
    if not auth or "." not in c:
        return False
    exp, sig = c.split(".", 1)
    try:
        if int(exp) < time.time():
            return False
    except ValueError:
        return False
    return hmac.compare_digest(sig, sign(auth["secret"], exp))


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


async def login(request):
    ip = request.client.host if request.client else "?"
    if request.method == "GET":
        return HTMLResponse(PAGE.replace("%MSG%", ""))
    rec = FAILS.get(ip, [0, 0])
    if rec[1] > time.time():
        return HTMLResponse(PAGE.replace("%MSG%", "<p>Too many tries. Wait 5 minutes.</p>"), status_code=429)
    form = parse_qs((await request.body()).decode("utf-8", "ignore"))
    pw = (form.get("pw") or [""])[0]
    auth = load_auth()
    ok = False
    if auth:
        ok = hmac.compare_digest(hash_pw(pw, bytes.fromhex(auth["salt"])).hex(), auth["hash"])
    if not ok:
        rec[0] += 1
        if rec[0] >= 5:
            rec = [0, time.time() + 300]
        FAILS[ip] = rec
        return HTMLResponse(PAGE.replace("%MSG%", "<p>Wrong password.</p>"), status_code=401)
    FAILS.pop(ip, None)
    resp = RedirectResponse("/hud.html", status_code=303)
    resp.set_cookie(COOKIE, make_cookie(auth), max_age=SESSION_SECONDS, httponly=True,
                    secure=True, samesite="lax", path="/")
    return resp


async def logout(request):
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


def pick(path):
    """Returns (base url, new path, forced headers)."""
    if path == "/helper" or path.startswith("/helper/"):
        return ("http://127.0.0.1:8765", path[len("/helper"):] or "/",
                {"host": "127.0.0.1:8765", "origin": "http://localhost:5173"})
    if path == "/wake" or path.startswith("/wake/"):
        return "http://127.0.0.1:8766", path[len("/wake"):] or "/", {"host": "127.0.0.1:8766"}
    if path.startswith("/v1") or path == "/health" or path.startswith("/api/"):
        return "http://127.0.0.1:8000", path, {"host": "localhost:8000"}
    return "http://localhost:5173", path, {"host": "localhost:5173"}


async def proxy(request):
    if not authed(request):
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return Response("login required", status_code=401)
    base, path, forced = pick(request.url.path)
    url = base + path + (("?" + request.url.query) if request.url.query else "")
    hdrs = {k: v for k, v in request.headers.items()
            if k not in HOP and k not in ("cookie", "origin", "referer")}
    hdrs.update(forced)
    body = None if request.method in ("GET", "HEAD") else request.stream()
    try:
        req = CLIENT.build_request(request.method, url, headers=hdrs, content=body)
        r = await CLIENT.send(req, stream=True)
    except httpx.HTTPError as e:
        return Response("backend not reachable: " + type(e).__name__, status_code=502)
    out = {k: v for k, v in r.headers.items() if k.lower() not in HOP}
    out["x-content-type-options"] = "nosniff"
    out["referrer-policy"] = "no-referrer"
    return StreamingResponse(r.aiter_raw(), status_code=r.status_code, headers=out,
                             background=BackgroundTask(r.aclose))


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    global CLIENT
    CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=5.0),
                               limits=httpx.Limits(max_connections=100))
    yield
    await CLIENT.aclose()


app = Starlette(
    routes=[Route("/login", login, methods=["GET", "POST"]),
            Route("/logout", logout, methods=["GET"]),
            Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])],
    lifespan=lifespan,
)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set-password", action="store_true")
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--no-tls", action="store_true", help="test only")
    a = ap.parse_args()
    if a.set_password:
        sys.exit(set_password())
    if not load_auth():
        print("No password set. Run:  python tools\\gateway.py --set-password")
        sys.exit(1)
    kw = {} if a.no_tls else {"ssl_certfile": str(GDIR / "cert.pem"), "ssl_keyfile": str(GDIR / "key.pem")}
    uvicorn.run(app, host="0.0.0.0", port=a.port, log_level="warning", **kw)
