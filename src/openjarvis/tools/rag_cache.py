"""Fast cache of the LM Studio Big RAG index, and search over it.

The Big RAG plugin stores its index as large JSON shards that are slow to read.
refresh() turns each changed shard into a .npy vector file plus a .jsonl passage
file; load_index() / load_passages() read that cache (kept in memory until it
changes), and search() / count_documents() answer questions from it.

Reads only SRC, writes only OUT. Data is read from JSON and numpy files only,
never executed. Rebuild by hand with: uv run --no-sync python tools\\ragcache.py
"""

from __future__ import annotations

import glob
import json
import logging
import os
import threading
import time
import urllib.request
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

SRC = r"C:\AI\Big-RAG"  # the Big RAG plugin's index
OUT = r"C:\AI\Big-RAG-cache"  # the fast cache written here
EMBED_URL = "http://localhost:1234/v1/embeddings"  # LM Studio
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"
REFRESH_EVERY = 60.0  # seconds between checks for changed shards


class Passage(TypedDict):
    text: str
    file: str  # file name shown to the user
    path: str  # full path of the source document
    chunk: int


# The .jsonl files keep short keys to stay small; only this module knows them.
_DISK_KEYS = {"text": "t", "file": "f", "path": "p", "chunk": "c"}


def _clean(s: object) -> str:
    """Text that is safe to write as UTF-8 (broken characters replaced)."""
    return str(s).encode("utf-8", "replace").decode("utf-8")


def _signature(path: str) -> list[int]:
    """File size + change time, to see whether an index.json changed."""
    st = os.stat(path)
    return [st.st_size, int(st.st_mtime)]


def _to_disk(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        _DISK_KEYS["text"]: _clean(metadata.get("text", "")),
        _DISK_KEYS["file"]: _clean(metadata.get("fileName", "")),
        _DISK_KEYS["path"]: _clean(metadata.get("filePath", "")),
        _DISK_KEYS["chunk"]: metadata.get("chunkIndex", 0),
    }


def _from_disk(row: dict[str, Any]) -> Passage:
    return {
        "text": row.get(_DISK_KEYS["text"], ""),
        "file": row.get(_DISK_KEYS["file"], ""),
        "path": row.get(_DISK_KEYS["path"], ""),
        "chunk": row.get(_DISK_KEYS["chunk"], 0),
    }


def _rebuild_shard(index_json: str, npy: str, jsonl: str) -> int:
    """Write one shard's vectors and passages (via .tmp files: never half-written)."""
    import numpy as np

    with open(index_json, encoding="utf-8") as f:
        items = json.load(f)["items"]
    vectors = np.array([it["vector"] for it in items], dtype=np.float32)
    with open(jsonl + ".tmp", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(_to_disk(it["metadata"]), ensure_ascii=False) + "\n")
    with open(npy + ".tmp", "wb") as f:
        np.save(f, vectors)
    os.replace(jsonl + ".tmp", jsonl)
    os.replace(npy + ".tmp", npy)
    return len(items)


def refresh(verbose: bool = True) -> int:
    """Rebuild the cache for every shard whose index.json changed; returns how many."""
    os.makedirs(OUT, exist_ok=True)
    rebuilt = 0
    for shard in sorted(glob.glob(os.path.join(SRC, "shard_*"))):
        index_json = os.path.join(shard, "index.json")
        if not os.path.exists(index_json):
            continue
        name = os.path.basename(shard)
        sig_file = os.path.join(OUT, name + ".sig.json")
        npy, jsonl = (
            os.path.join(OUT, name + ".npy"),
            os.path.join(OUT, name + ".jsonl"),
        )
        current = _signature(index_json)
        try:
            if all(os.path.exists(p) for p in (sig_file, npy, jsonl)):
                with open(sig_file, encoding="utf-8") as f:
                    if json.load(f) == current:
                        continue
            count = _rebuild_shard(index_json, npy, jsonl)
            with open(sig_file, "w", encoding="utf-8") as f:
                json.dump(current, f)
            rebuilt += 1
            if verbose:
                print(name, "rebuilt:", count, "passages", flush=True)
        except (
            OSError,
            ValueError,
            KeyError,
        ) as exc:  # a shard LM Studio is still writing
            logger.debug("shard %s skipped: %s", name, exc)
            if verbose:
                print(
                    name,
                    "skipped (will retry):",
                    _clean(exc).encode("ascii", "replace").decode()[:100],
                )
    return rebuilt


# ---------------------------------------------------------------------------- reading
_lock = threading.Lock()
_index: dict[str, Any] = {"sig": None, "vectors": None, "passages": []}
_texts: dict[str, Any] = {"sig": None, "passages": []}
_last_refresh = {"at": 0.0}


def _maybe_refresh(every: float) -> None:
    if time.time() - _last_refresh["at"] > every:
        try:
            refresh(verbose=False)
        except OSError as exc:  # cache folder not writable: keep serving the old cache
            logger.debug("rag cache refresh failed: %s", exc)
        _last_refresh["at"] = time.time()


def _shards(ext: str) -> tuple[list[str], tuple[tuple[str, float], ...]]:
    files = sorted(glob.glob(os.path.join(OUT, "shard_*" + ext)))
    return files, tuple((f, os.stat(f).st_mtime) for f in files)


def _read_passages(jsonl: str) -> list[Passage]:
    with open(jsonl, encoding="utf-8") as f:
        return [_from_disk(json.loads(line)) for line in f]


def load_index(
    refresh_every: float = REFRESH_EVERY,
) -> tuple[np.ndarray, list[Passage]]:
    """All passage vectors (one row each) and passages; reloaded on change."""
    import numpy as np

    with _lock:
        _maybe_refresh(refresh_every)
        files, sig = _shards(".npy")
        if sig != _index["sig"]:
            passages: list[Passage] = []
            vectors = []
            for npy in files:
                vectors.append(np.load(npy))
                passages.extend(_read_passages(npy[:-4] + ".jsonl"))
            matrix = (
                np.concatenate(vectors)
                if vectors
                else np.zeros((0, 0), dtype=np.float32)
            )
            _index.update(sig=sig, vectors=matrix, passages=passages)
        return _index["vectors"], _index["passages"]


def load_passages(refresh_every: float = REFRESH_EVERY) -> list[Passage]:
    """Only the passage texts (no vectors: much less memory); reloaded on change."""
    with _lock:
        _maybe_refresh(refresh_every)
        files, sig = _shards(".jsonl")
        if sig != _texts["sig"]:
            passages: list[Passage] = []
            for jsonl in files:
                passages.extend(_read_passages(jsonl))
            _texts.update(sig=sig, passages=passages)
        return _texts["passages"]


def embed_batch(texts: list[str], timeout: float = 60.0) -> list[list[float]]:
    """Raw vectors for several texts from the LM Studio embedding model, in order.

    The one LM Studio embedding client: embed_query() below and the memory store's
    LMStudioEmbedder (tools/storage/sqlite_dense.py) both use it.
    """
    body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        EMBED_URL, data=body, headers={"Content-Type": "application/json"}
    )
    # Fixed http://localhost URL: no user-controlled scheme reaches urlopen.
    with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
        data = json.load(r)["data"]
    return [row["embedding"] for row in sorted(data, key=lambda d: d.get("index", 0))]


def embed_query(text: str, timeout: float = 60.0) -> np.ndarray:
    """The question as a normalized vector from the LM Studio embedding model."""
    import numpy as np

    vector = np.array(embed_batch([text], timeout)[0], dtype=np.float32)
    return vector / np.linalg.norm(vector)


def search(
    query: str, k: int = 4, min_score: float = 0.0, timeout: float = 60.0
) -> list[tuple[float, Passage]]:
    """The k passages closest in meaning to the query, best first, >= min_score."""
    import numpy as np

    vectors, passages = load_index()
    if not passages:
        return []
    scores = vectors @ embed_query(query, timeout)
    k = min(k, len(scores))
    best = np.argpartition(-scores, k - 1)[:k]
    best = best[np.argsort(-scores[best])]
    return [
        (float(scores[i]), passages[i]) for i in best if float(scores[i]) >= min_score
    ]


_lowered: dict[str, Any] = {
    "source": None,
    "texts": [],
}  # lower-case texts, made once per load


def _lower_texts(passages: list[Passage]) -> list[str]:
    if _lowered["source"] is not passages:
        _lowered.update(source=passages, texts=[p["text"].lower() for p in passages])
    return _lowered["texts"]


def count_documents(
    words: list[str], passages: list[Passage] | None = None
) -> tuple[int, dict[str, int]]:
    """(passages containing every word, {file name: matching passages}), any case."""
    wanted = [w.lower() for w in words if w]
    pool = load_passages() if passages is None else passages
    files: dict[str, int] = {}
    matches = 0
    if not wanted:
        return 0, files
    for p, text in zip(pool, _lower_texts(pool)):
        if all(w in text for w in wanted):
            matches += 1
            files[p["file"]] = files.get(p["file"], 0) + 1
    return matches, files


def top_documents(files: dict[str, int], n: int = 15) -> list[tuple[str, int]]:
    """The n files with the most matching passages."""
    return sorted(files.items(), key=lambda kv: -kv[1])[:n]
