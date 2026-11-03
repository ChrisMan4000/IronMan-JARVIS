"""Jarvis hardware helper (port 8765, this PC only).

Serves the HUD: live stats (GET /), document links and word counts, model control,
and HUD shortcuts for Hue, Tado, news and web search. Start it with:
  uv run --no-sync python tools\\hwstats.py

The parts live next to this file: helper_http (who may ask, how answers are sent),
helper_stats (the live numbers), helper_models (model control) and helper_docs
(documents). An optional hwstats_private.py (not in the repo) can add more routes.
Security rules are in helper_http; routes that change something are HUD-only.
"""

from __future__ import annotations

import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import helper_docs
import helper_models
import helper_stats
from helper_http import (
    PORT,
    Route,
    host_ok,
    need_trusted,
    query,
    send,
    trusted_tool_route,
)

logger = logging.getLogger(__name__)

NEWS_LIMIT = (1, 10)
QUERY_CHARS = {"room": 60, "state": 5, "search": 200}
SEARCH_REPLY_CHARS = 6000


# --------------------------------------------------------- HUD shortcuts (HUD only)
def _hue(q: dict[str, str]) -> Any:
    """/hue?room=<text>&state=on|off -> switch a Hue room (same code as hue_set)."""
    from openjarvis.tools.hue_set import HueSetTool

    return HueSetTool().execute(
        room=q.get("room", "")[: QUERY_CHARS["room"]],
        state=q.get("state", "")[: QUERY_CHARS["state"]],
    )


def _tado(q: dict[str, str]) -> Any:
    """/tado?action=resume|off&room=<name> -> Tado heating (other actions refused)."""
    if q.get("action", "") not in ("resume", "off"):
        return {"ok": False, "text": "refused: only resume and off are allowed here"}
    from openjarvis.tools.tado_heating import TadoHeatingTool

    return TadoHeatingTool().execute(
        action=q["action"], room=q.get("room", "")[: QUERY_CHARS["room"]]
    )


def news_limit(raw: str) -> int:
    try:
        return max(NEWS_LIMIT[0], min(NEWS_LIMIT[1], int(raw)))
    except ValueError:
        return 5


def _news(q: dict[str, str]) -> Any:
    """/news?feed=<short name>&limit=<1-10> -> headlines (built-in feed names only)."""
    from openjarvis.tools.rss_news import FEEDS, RssNewsTool

    feed = q.get("feed", "")
    if feed not in FEEDS:
        return {"ok": False, "text": "unknown feed name"}
    return RssNewsTool().execute(feed=feed, limit=news_limit(q.get("limit", "5")))


def _search(q: dict[str, str]) -> Any:
    """/search?q=<text> -> web_search result (fallback when the model skipped it)."""
    text = q.get("q", "").strip()[: QUERY_CHARS["search"]]
    if not text:
        return {"ok": False, "text": "empty query"}
    from openjarvis.tools.web_search import WebSearchTool

    return WebSearchTool().execute(query=text, max_results=5)


# --------------------------------------------------------------------------- routes
ROUTES: dict[str, Route] = {
    "/": lambda h: send(h, 200, helper_stats.stats),
    "/hue": trusted_tool_route("hue", _hue),
    "/tado": trusted_tool_route("tado", _tado),
    "/news": trusted_tool_route("news", _news),
    "/search": trusted_tool_route("search", _search, SEARCH_REPLY_CHARS),
    "/count": helper_docs.serve_count,
    "/docexists": helper_docs.serve_docexists,
    "/doc": helper_docs.serve_doc,
}


def private_routes() -> dict[str, Route]:
    """Extra routes from an optional hwstats_private.py next to this file."""
    try:
        import hwstats_private
    except ImportError:
        return {}
    if hasattr(hwstats_private, "routes"):
        return hwstats_private.routes()
    # An older private file expects the three web helpers handed over by setup().
    return hwstats_private.setup(
        {"need_trusted": need_trusted, "query": query, "send": send}
    )


class HelperHandler(BaseHTTPRequestHandler):
    """Routes GET requests. Anything with a wrong Host header is refused first."""

    routes: dict[str, Route] = ROUTES

    def do_GET(self) -> None:
        if not host_ok(self):
            return send(self, 403, {"error": "bad host"})
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/m/"):
            return helper_models.serve_model_api(self)
        route = self.routes.get(path)
        if route is None:
            return send(self, 404, {"error": "not found"})
        return route(self)

    def log_message(self, *args: Any) -> None:  # keep the console quiet
        pass


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s %(name)s: %(message)s"
    )
    HelperHandler.routes = {
        **ROUTES,
        **private_routes(),
    }  # a private route may replace one
    helper_stats.start()
    helper_models.start()
    print("Hardware stats on http://127.0.0.1:%d" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), HelperHandler).serve_forever()


if __name__ == "__main__":
    main()
