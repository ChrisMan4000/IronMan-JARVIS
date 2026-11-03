"""sqlite_dense memory: mirror rebuild, staleness, SQLite fallback, store/rebuild race.

The real SQLiteMemory needs the native Rust extension, so these tests give the
class a tiny pure-Python SQLite parent with the same table layout.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid

import pytest

np = pytest.importorskip("numpy")

from openjarvis.tools.storage import sqlite_dense  # noqa: E402
from openjarvis.tools.storage._stubs import RetrievalResult  # noqa: E402
from openjarvis.tools.storage.embeddings import Embedder  # noqa: E402

WORDS = ("hue", "tado", "oxxify", "pineapple")


class WordEmbedder(Embedder):
    """Vector = which of four words a text contains; can be slowed or switched off."""

    def __init__(self) -> None:
        self.calls = 0
        self.delay = 0.0
        self.offline = False

    def embed(self, texts):
        self.calls += 1
        if self.offline:
            raise ConnectionError("LM Studio not running")
        time.sleep(self.delay)
        rows = (
            np.array(
                [[float(w in t.lower()) for w in WORDS] for t in texts],
                dtype=np.float32,
            )
            + 1e-3
        )
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)

    def dim(self):
        return len(WORDS)


class PySQLiteParent:
    """Stand-in for the Rust-backed SQLiteMemory: same table, simple LIKE search."""

    def __init__(self, db_path=""):
        self._db_path = str(db_path)
        with sqlite3.connect(self._db_path) as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS documents"
                " (id TEXT, content TEXT, source TEXT, metadata TEXT)"
            )

    def _run(self, sql, args=()):
        with sqlite3.connect(self._db_path) as c:
            return c.execute(sql, args).fetchall()

    def store(self, content, *, source="", metadata=None):
        doc_id = uuid.uuid4().hex
        self._run(
            "INSERT INTO documents VALUES (?,?,?,?)",
            (doc_id, content, source, json.dumps(metadata or {})),
        )
        return doc_id

    def replace_source(self, source, documents):
        self._run("DELETE FROM documents WHERE source = ?", (source,))
        return [self.store(c, source=source, metadata=m) for c, m in documents]

    def delete(self, doc_id):
        self._run("DELETE FROM documents WHERE id = ?", (doc_id,))
        return True

    def clear(self):
        self._run("DELETE FROM documents")

    def retrieve(self, query, *, top_k=5, **kwargs):
        rows = self._run(
            "SELECT content, source FROM documents WHERE content LIKE ?",
            ("%" + query + "%",),
        )
        return [RetrievalResult(content=c, source=s, score=-1.0) for c, s in rows][
            :top_k
        ]


@pytest.fixture
def memory(tmp_path, monkeypatch):
    for name in ("__init__", "store", "replace_source", "delete", "clear", "retrieve"):
        monkeypatch.setattr(
            sqlite_dense.SQLiteMemory, name, getattr(PySQLiteParent, name)
        )
    monkeypatch.setattr(
        sqlite_dense.SQLiteMemory, "_run", PySQLiteParent._run, raising=False
    )
    emb = WordEmbedder()
    return sqlite_dense.SQLiteDenseMemory(tmp_path / "memory.db", embedder=emb), emb


def _contents(results):
    return [r.content for r in results]


def test_first_use_rebuilds_from_sqlite_then_stores_incrementally(memory):
    mem, emb = memory
    PySQLiteParent.store(
        mem, "Hue bridge notes"
    )  # already on disk before the mirror exists
    assert _contents(mem.retrieve("hue", top_k=1)) == ["Hue bridge notes"]
    calls = emb.calls
    mem.store("Tado token lives in tado-token.json")
    assert emb.calls == calls + 1  # one embedding for the new document, no rebuild
    assert _contents(mem.retrieve("tado", top_k=1)) == [
        "Tado token lives in tado-token.json"
    ]


def test_delete_and_replace_mark_the_mirror_stale(memory):
    mem, _emb = memory
    doc = mem.store("pineapple test note")
    mem.store("oxxify vent", source="vent")
    mem.delete(doc)
    assert "pineapple test note" not in _contents(mem.retrieve("pineapple", top_k=5))
    mem.replace_source("vent", [("oxxify filter changed", None)])
    assert _contents(mem.retrieve("oxxify", top_k=5))[0] == "oxxify filter changed"


def test_falls_back_to_sqlite_when_embeddings_fail(memory):
    mem, emb = memory
    mem.store("hue lamp list")
    emb.offline = True
    mem.store("hue room list")  # stored in SQLite even though the mirror cannot follow
    results = mem.retrieve("room")
    assert (
        _contents(results) == ["hue room list"] and results[0].score == -1.0
    )  # SQLite answer
    emb.offline = False
    assert set(_contents(mem.retrieve("hue", top_k=5))) == {
        "hue lamp list",
        "hue room list",
    }


def test_store_during_rebuild_is_neither_lost_nor_doubled(memory):
    mem, emb = memory
    for i in range(3):
        PySQLiteParent.store(mem, "tado note %d" % i)
    emb.delay = 0.2  # slow rebuild
    reader = threading.Thread(target=lambda: mem.retrieve("tado"))
    reader.start()
    time.sleep(0.05)  # the rebuild is running now
    mem.store("tado note new")
    reader.join()
    emb.delay = 0.0
    found = _contents(mem.retrieve("tado", top_k=10))
    assert sorted(found) == [
        "tado note 0",
        "tado note 1",
        "tado note 2",
        "tado note new",
    ]
