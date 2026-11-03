"""Try the document search from a terminal, without the model or the HUD.

uv run --no-sync python tools\\ragsearch.py climate change
"""

import sys
import time

from openjarvis.tools import rag_cache


def _ascii(s: object, n: int = 400) -> str:
    """Printable on any Windows console."""
    return str(s).encode("ascii", "replace").decode().replace("\n", " ")[:n]


def main(words: list[str]) -> None:
    t0 = time.time()
    rebuilt = rag_cache.refresh(verbose=False)
    if rebuilt:
        print("refreshed shards:", rebuilt)
    _, passages = rag_cache.load_index(refresh_every=float("inf"))
    print("passages loaded:", len(passages), "in %.1fs" % (time.time() - t0))
    t1 = time.time()
    for score, p in rag_cache.search(
        " ".join(words) or "climate change", k=5, timeout=120
    ):
        print("%.3f  %s (chunk %s)" % (score, _ascii(p["file"], 80), p["chunk"]))
        print("      " + _ascii(p["text"]))
    print("search took %.2fs" % (time.time() - t1))


if __name__ == "__main__":
    main(sys.argv[1:])
