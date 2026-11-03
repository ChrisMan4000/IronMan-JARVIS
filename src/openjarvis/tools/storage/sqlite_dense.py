"""SQLite + dense (meaning-based) memory backend.

Added for the IronMan J.A.R.V.I.S. project. SQLite keeps the data on disk; a
DenseMemory mirror (LM Studio embeddings) is rebuilt from SQLite on first use and
after deletes or source replacements. If embedding fails, retrieval falls back to
plain SQLite search and the mirror is rebuilt on the next call.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from openjarvis.core.registry import MemoryRegistry
from openjarvis.tools import rag_cache
from openjarvis.tools.storage._stubs import RetrievalResult
from openjarvis.tools.storage.dense import DenseMemory
from openjarvis.tools.storage.embeddings import Embedder
from openjarvis.tools.storage.sqlite import SQLiteMemory

logger = logging.getLogger(__name__)


class LMStudioEmbedder(Embedder):
    """Embeddings from LM Studio's embedding model, through rag_cache.embed_batch.

    The endpoint and the model name live only in openjarvis.tools.rag_cache.
    """

    BATCH_SIZE = 16  # texts per request

    def __init__(self, timeout: float = 60.0) -> None:
        self._timeout = timeout
        self._dim: int | None = None

    def embed(self, texts: list[str]) -> Any:
        """Rows of L2-normalized float32 vectors, one per text (shape (n, dim))."""
        import numpy as np  # optional dependency, only needed once embeddings are used

        if not texts:
            return np.zeros((0, self.dim()), dtype=np.float32)
        rows: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            rows.extend(rag_cache.embed_batch(batch, self._timeout))
        arr = np.asarray(rows, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        arr = arr / np.where(norms == 0, 1.0, norms)
        self._dim = int(arr.shape[1])
        return arr

    def dim(self) -> int:
        """Vector size (asks LM Studio once with a short probe text)."""
        if self._dim is None:
            self._dim = len(rag_cache.embed_batch(["probe"], self._timeout)[0])
        return self._dim


def _metadata(raw: str | None) -> dict[str, Any] | None:
    try:
        return json.loads(raw) if raw else None
    except ValueError:  # a damaged row keeps its text, loses only its metadata
        return None


@MemoryRegistry.register("sqlite_dense")
class SQLiteDenseMemory(SQLiteMemory):
    """SQLite storage with a meaning-based mirror; every change goes through one lock.

    The lock covers both the SQLite write and the mirror update, so a document
    stored while the mirror is being rebuilt is neither lost nor added twice.
    """

    backend_id = "sqlite_dense"

    def __init__(
        self, db_path: str | Path = "", embedder: Embedder | None = None
    ) -> None:
        super().__init__(db_path)
        self._dense = DenseMemory(embedder=embedder or LMStudioEmbedder())
        self._ready = (
            False  # mirror matches SQLite; only read or written with _dlock held
        )
        self._dlock = threading.RLock()

    def _rebuild_locked(self) -> None:
        """Refill the mirror from SQLite in batches (call with _dlock held)."""
        self._dense.clear()
        conn = sqlite3.connect(self._db_path)
        try:
            rows = conn.execute(
                "SELECT content, source, metadata FROM documents"
            ).fetchall()
        finally:
            conn.close()
        if rows:
            self._dense.store_many(
                [content for content, _s, _m in rows],
                sources=[source or "" for _c, source, _m in rows],
                metadatas=[_metadata(meta) or {} for _c, _s, meta in rows],
            )
        self._ready = True

    def _ensure(self) -> None:
        with self._dlock:
            if not self._ready:
                self._rebuild_locked()

    def _mark_stale(self) -> None:
        with self._dlock:
            self._ready = False

    def store(
        self, content: str, *, source: str = "", metadata: dict[str, Any] | None = None
    ) -> str:
        with self._dlock:
            doc_id = super().store(content, source=source, metadata=metadata)
            try:
                if self._ready:
                    self._dense.store(content, source=source, metadata=metadata)
                else:
                    self._rebuild_locked()  # includes the row just stored
            except Exception as exc:  # embedding server down: SQLite still has the row
                self._ready = False
                logger.warning("dense mirror store failed: %s", exc)
        return doc_id

    def replace_source(
        self, source: str, documents: list[tuple[str, dict[str, Any] | None]]
    ) -> list[str]:
        with self._dlock:
            ids = super().replace_source(source, documents)
            self._ready = False
        return ids

    def delete(self, doc_id: str) -> bool:
        with self._dlock:
            ok = super().delete(doc_id)
            self._ready = False
        return ok

    def clear(self) -> None:
        with self._dlock:
            super().clear()
            self._ready = False

    def retrieve(
        self, query: str, *, top_k: int = 5, **kwargs: Any
    ) -> list[RetrievalResult]:
        try:
            self._ensure()
            return self._dense.retrieve(
                query, top_k=top_k
            )  # DenseMemory has its own lock
        except Exception as exc:  # embedding server down: answer from SQLite instead
            self._mark_stale()
            logger.warning("dense retrieve failed, using sqlite: %s", exc)
            return super().retrieve(query, top_k=top_k)
