"""Small files the HUD reads through the helper: when a search tool last ran, and
the web addresses the last web_search returned (IronMan J.A.R.V.I.S.).

The HUD shows these as the WEB / DOC lights and adds a "Links:" line when a small
model forgot to write one.
"""

from __future__ import annotations

import logging
import os
import re
import time

logger = logging.getLogger(__name__)

JARVIS_DIR = os.path.join(os.path.expanduser("~"), ".openjarvis")
WEB_LINKS_FILE = os.path.join(JARVIS_DIR, "tool-web_search-links.txt")
MAX_LINKS = 3
_URL = re.compile(r"https?://[^\s\"'<>()\[\]{}|\\^`]+")


def result_links(text: str, limit: int = MAX_LINKS) -> list[str]:
    """The first different web addresses in a tool result, in order."""
    links: list[str] = []
    for url in _URL.findall(text or ""):
        url = url.rstrip(".,;:!?")
        if url not in links:
            links.append(url)
        if len(links) == limit:
            break
    return links


def save_web_links(text: str) -> bool:
    """Write "<time>" and the result's links (one per line) for the helper; False if
    the file could not be written (the answer itself is not affected)."""
    lines = [str(time.time()), *result_links(text)]
    try:
        with open(WEB_LINKS_FILE + ".tmp", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(WEB_LINKS_FILE + ".tmp", WEB_LINKS_FILE)
    except OSError as exc:
        logger.debug("web links not saved: %s", exc)
        return False
    return True
