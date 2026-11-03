"""HTTP basics of the Jarvis helper (port 8765): who may ask, and how answers are sent.

Security rules:
- Only requests with Host 127.0.0.1:8765 or localhost:8765 are answered
  (blocks DNS-rebinding attacks from websites).
- Routes that CHANGE something or fetch from the internet only work when the
  request comes from the HUD page (Origin or Referer = http://localhost:5173).
- Other websites cannot READ the answers: the CORS header is only sent to the HUD.

Used by hwstats.py, the other helper_* modules and the optional hwstats_private.py.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from typing import Any

PORT = 8765
ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
ALLOWED_HOSTS = ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)

Handler = BaseHTTPRequestHandler
Route = Callable[[Handler], Any]


def host_ok(h: Handler) -> bool:
    """True when the Host header is this helper (stops DNS rebinding)."""
    return h.headers.get("Host", "").strip().lower() in ALLOWED_HOSTS


def trusted_origin(h: Handler) -> str | None:
    """The HUD origin the request came from, or None.

    If an Origin header exists it must be allowed; otherwise the Referer must be the
    HUD page (exact origin, followed by / or nothing).
    """
    origin = h.headers.get("Origin", "")
    if origin:
        return origin if origin in ALLOWED_ORIGINS else None
    ref = h.headers.get("Referer", "")
    for allowed in ALLOWED_ORIGINS:
        if ref == allowed or ref.startswith(allowed + "/"):
            return allowed
    return None


def send(
    h: Handler,
    code: int,
    body: Any,
    ctype: str = "application/json",
    extra: dict[str, str] | None = None,
) -> None:
    """Send one response. The CORS header is added only for the HUD."""
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("X-Content-Type-Options", "nosniff")
    origin = trusted_origin(h)
    if origin:
        h.send_header("Access-Control-Allow-Origin", origin)
        h.send_header("Vary", "Origin")
    for k, v in (extra or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)


def need_trusted(h: Handler) -> bool:
    """For routes that change something: 403 unless the request is from the HUD."""
    if trusted_origin(h) is None:
        send(
            h,
            403,
            {
                "ok": False,
                "text": "refused: request did not come from the HUD",
                "error": "forbidden",
            },
        )
        return False
    return True


def query(h: Handler) -> dict[str, str]:
    """URL query string as a simple dict (first value of each key)."""
    return {
        k: v[0]
        for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query).items()
    }


def tool_reply(
    label: str, run: Callable[[], Any], max_chars: int | None = None
) -> dict[str, Any]:
    """{"ok", "text"} from a ToolResult; a crash becomes "<label> error: <type>".

    run may also return a ready {"ok", "text"} dict (a request it refused itself).
    """
    try:
        result = run()
        if isinstance(result, dict):
            return result
        text = str(result.content)
        return {
            "ok": bool(result.success),
            "text": text[:max_chars] if max_chars else text,
        }
    except Exception as exc:  # the HUD shows the text; it must never see a stack trace
        return {"ok": False, "text": "%s error: %s" % (label, type(exc).__name__)}


def trusted_tool_route(
    label: str,
    call: Callable[[dict[str, str]], Any | dict[str, Any]],
    max_chars: int | None = None,
) -> Route:
    """A HUD-only route that runs call(query) and answers with tool_reply.

    call may return a ToolResult (wrapped by tool_reply) or a ready {"ok", "text"}
    dict, for requests it refuses itself.
    """

    def route(h: Handler) -> None:
        if not need_trusted(h):
            return
        q = query(h)
        reply = tool_reply(label, lambda: call(q), max_chars)
        send(h, 200, reply)

    return route
