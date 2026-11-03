"""Documents of the ORACLE library for the HUD: /doc, /docexists and /count.

Only files inside the ORACLE folder are ever served (links are resolved first), and
file types that could run scripts in the browser are sent as plain text.
"""

from __future__ import annotations

import mimetypes
import os
import threading
import time
from typing import Any

from helper_http import Handler, query, send

from openjarvis.tools import rag_cache

DOC_ROOT = os.environ.get("JARVIS_DOC_ROOT") or os.path.join(
    os.path.expanduser("~"), "Documents", "ORACLE"
)
DOC_MAP_REFRESH = 600  # seconds between re-reads of the folder
COUNT_REFRESH = 600  # seconds between checks for a changed document index
ACTIVE_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "image/svg+xml",
    "text/xml",
    "application/xml",
    "application/javascript",
    "text/javascript",
}


class DocIndex:
    """Lower-case file name -> full path of every ORACLE file, re-read every
    DOC_MAP_REFRESH seconds (one walk at a time, readers get a finished map)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._read_at = 0.0
        self._names: dict[str, str] = {}

    def forget(self) -> None:
        """Walk the folder again on the next lookup."""
        with self._lock:
            self._read_at = 0.0

    def names(self) -> dict[str, str]:
        with self._lock:
            if time.time() - self._read_at > DOC_MAP_REFRESH:
                names: dict[str, str] = {}
                for root, _dirs, files in os.walk(DOC_ROOT):
                    for f in files:
                        names.setdefault(f.lower(), os.path.join(root, f))
                self._names, self._read_at = names, time.time()
            return self._names


doc_index = DocIndex()


def inside_root(path: str) -> bool:
    """True only when the real path (links resolved) is inside the ORACLE folder."""
    try:
        root = os.path.normcase(os.path.realpath(DOC_ROOT))
        p = os.path.normcase(os.path.realpath(path))
        return os.path.commonpath([root, p]) == root
    except ValueError:  # different drives on Windows
        return False


def find_doc(name: str | None) -> str | None:
    """Full path of a document by file name (exact, else unique partial), or None."""
    name = (name or "").strip().lower()
    if not name:
        return None
    names = doc_index.names()
    path = names.get(name)
    if not path:
        hits = [p for k, p in names.items() if name in k or k in name]
        path = hits[0] if len(hits) == 1 else None
    return path if path and inside_root(path) else None


def safe_content_type(path: str) -> str:
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return "text/plain; charset=utf-8" if ctype.split(";")[0] in ACTIVE_TYPES else ctype


def serve_docexists(h: Handler) -> None:
    """/docexists?f=<file> -> {"exists": true/false}"""
    send(h, 200, {"exists": bool(find_doc(query(h).get("f", "")))})


def serve_doc(h: Handler) -> None:
    """/doc?f=<file> -> the document itself (only from inside the ORACLE folder)."""
    path = find_doc(query(h).get("f", ""))
    if not path:
        return send(h, 404, b"not found", "text/plain")
    with open(path, "rb") as fh:
        data = fh.read()
    fname = os.path.basename(path).encode("ascii", "replace").decode().replace('"', "'")
    send(
        h,
        200,
        data,
        safe_content_type(path),
        {"Content-Disposition": 'inline; filename="%s"' % fname},
    )


def count_word(word: str) -> dict[str, Any]:
    """How many documents / passages contain the word, plus the top 15 documents."""
    passages, files = rag_cache.count_documents(
        [word], rag_cache.load_passages(COUNT_REFRESH)
    )
    return {
        "word": word,
        "documents": len(files),
        "passages": passages,
        "top": [{"f": f, "n": c} for f, c in rag_cache.top_documents(files)],
    }


def serve_count(h: Handler) -> None:
    """/count?w=<word> -> JSON with the counts."""
    w = query(h).get("w", "").strip()[:60]
    send(h, 200, count_word(w) if w else {"error": "no word"})
