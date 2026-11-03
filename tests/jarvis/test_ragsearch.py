"""tools/ragsearch.py: the terminal document-search test prints scores and files."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
if TOOLS not in sys.path:
    sys.path.append(TOOLS)

import ragsearch  # noqa: E402


def test_main_prints_hits(monkeypatch, capsys):
    passage = {
        "text": "Sea levels rise.\nFast.",
        "file": "Climate report.pdf",
        "path": "",
        "chunk": 3,
    }
    monkeypatch.setattr(ragsearch.rag_cache, "refresh", lambda verbose=False: 0)
    monkeypatch.setattr(
        ragsearch.rag_cache, "load_index", lambda refresh_every=0: (None, [passage])
    )
    seen = {}

    def fake_search(query, k=4, min_score=0.0, timeout=60.0):
        seen.update(query=query, k=k)
        return [(0.912, passage)]

    monkeypatch.setattr(ragsearch.rag_cache, "search", fake_search)
    ragsearch.main(["sea", "level"])
    out = capsys.readouterr().out
    assert seen == {"query": "sea level", "k": 5}
    assert (
        "0.912  Climate report.pdf (chunk 3)" in out and "Sea levels rise. Fast." in out
    )


def test_ascii_output_is_safe_for_any_console():
    assert ragsearch._ascii("Café ☕\nnext", 8) == "Caf? ? n"
