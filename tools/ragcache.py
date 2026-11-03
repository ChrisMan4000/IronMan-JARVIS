"""Rebuild the fast Big RAG cache by hand (oracle_search also does it by itself).

  uv run --no-sync python tools\\ragcache.py

Reads only C:\\AI\\Big-RAG, writes only C:\\AI\\Big-RAG-cache. The code lives in
openjarvis.tools.rag_cache.
"""

from openjarvis.tools.rag_cache import refresh

if __name__ == "__main__":
    print("DONE, shards rebuilt:", refresh())
