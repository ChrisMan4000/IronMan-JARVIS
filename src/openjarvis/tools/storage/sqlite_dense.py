"""SQLite + dense (meaning-based) memory backend.
Added for the IronMan J.A.R.V.I.S. project. SQLite keeps the data on disk;
a DenseMemory mirror (LM Studio embeddings) is rebuilt from SQLite on first use.
If embedding fails, it falls back to plain SQLite search."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from openjarvis.core.registry import MemoryRegistry
from openjarvis.tools.storage.dense import DenseMemory
from openjarvis.tools.storage.embeddings import OllamaEmbedder
from openjarvis.tools.storage.sqlite import SQLiteMemory

logger = logging.getLogger(__name__)


class LMStudioEmbedder(OllamaEmbedder):
    """Embeddings from LM Studio (/v1/embeddings) instead of Ollama."""

    def __init__(self) -> None:
        super().__init__(
            model="text-embedding-nomic-embed-text-v1.5",
            base_url="http://localhost:1234",
            batch_size=16,
            max_parallel=2,
        )

    def _embed_batch(self, texts):
        r = self._httpx.post(
            self._base_url + "/v1/embeddings",
            json={"model": self._model, "input": texts},
            timeout=self._timeout_s,
        )
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]


@MemoryRegistry.register("sqlite_dense")
class SQLiteDenseMemory(SQLiteMemory):
    backend_id = "sqlite_dense"

    def __init__(self, db_path="", embedder=None) -> None:
        super().__init__(db_path)
        self._dense = DenseMemory(embedder=embedder or LMStudioEmbedder())
        self._ready = False
        self._dlock = threading.Lock()

    def _ensure(self) -> None:
        if self._ready:
            return
        with self._dlock:
            if self._ready:
                return
            self._dense.clear()
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT content, source, metadata FROM documents"
                ).fetchall()
            finally:
                conn.close()
            for content, source, meta in rows:
                try:
                    md = json.loads(meta) if meta else None
                except Exception:
                    md = None
                self._dense.store(content, source=source or "", metadata=md)
            self._ready = True

    def store(self, content, *, source="", metadata=None):
        was_ready = self._ready
        doc_id = super().store(content, source=source, metadata=metadata)
        try:
            if was_ready:
                self._dense.store(content, source=source, metadata=metadata)
            else:
                self._ensure()
        except Exception as exc:
            self._ready = False
            logger.warning("dense mirror store failed: %s", exc)
        return doc_id

    def replace_source(self, source, documents):
        ids = super().replace_source(source, documents)
        self._ready = False
        return ids

    def delete(self, doc_id):
        ok = super().delete(doc_id)
        self._ready = False
        return ok

    def clear(self) -> None:
        super().clear()
        self._ready = False

    def retrieve(self, query, *, top_k=5, **kwargs):
        try:
            self._ensure()
            return self._dense.retrieve(query, top_k=top_k)
        except Exception as exc:
            self._ready = False
            logger.warning("dense retrieve failed, using sqlite: %s", exc)
            return super().retrieve(query, top_k=top_k)