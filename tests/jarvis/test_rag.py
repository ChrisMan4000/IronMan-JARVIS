"""Document search: cache rebuild, loading, counting, semantic search and the tool."""

from __future__ import annotations

import json
import os
import urllib.error

import pytest

np = pytest.importorskip("numpy")

from openjarvis.tools import oracle_search, rag_cache  # noqa: E402

ITEMS = [
    ("Climate report.pdf", 0, "Sea levels rise as the climate warms.", [1.0, 0.0, 0.0]),
    ("Climate report.pdf", 1, "Glaciers melt faster each decade.", [0.8, 0.6, 0.0]),
    ("Cookbook.pdf", 0, "Bake the bread at 220 degrees.", [0.0, 0.0, 1.0]),
]


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A Big RAG folder with one shard, and an empty cache folder."""
    src, out = tmp_path / "Big-RAG", tmp_path / "Big-RAG-cache"
    shard = src / "shard_000"
    shard.mkdir(parents=True)
    items = [
        {
            "vector": v,
            "metadata": {
                "text": t,
                "fileName": f,
                "filePath": "C:/docs/" + f,
                "chunkIndex": c,
            },
        }
        for f, c, t, v in ITEMS
    ]
    (shard / "index.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    monkeypatch.setattr(rag_cache, "SRC", str(src))
    monkeypatch.setattr(rag_cache, "OUT", str(out))
    for cache in (rag_cache._index, rag_cache._texts):
        cache["sig"] = None
    monkeypatch.setitem(rag_cache._last_refresh, "at", 0.0)
    monkeypatch.setattr(
        rag_cache,
        "embed_query",
        lambda text, timeout=60.0: np.array([1.0, 0.0, 0.0], dtype=np.float32),
    )
    return shard


def test_refresh_builds_once_and_rebuilds_on_change(library):
    assert rag_cache.refresh(verbose=False) == 1
    assert sorted(os.listdir(rag_cache.OUT)) == [
        "shard_000.jsonl",
        "shard_000.npy",
        "shard_000.sig.json",
    ]
    assert rag_cache.refresh(verbose=False) == 0  # unchanged: nothing to do
    index = library / "index.json"
    index.write_text(index.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert rag_cache.refresh(verbose=False) == 1


def test_broken_shard_is_skipped_and_retried(library, capsys):
    (library / "index.json").write_text("{not json", encoding="utf-8")
    assert rag_cache.refresh(verbose=True) == 0
    assert "skipped (will retry)" in capsys.readouterr().out


def test_load_index_decodes_passages(library):
    vectors, passages = rag_cache.load_index()
    assert vectors.shape == (3, 3)
    assert passages[0] == {
        "text": "Sea levels rise as the climate warms.",
        "file": "Climate report.pdf",
        "path": "C:/docs/Climate report.pdf",
        "chunk": 0,
    }
    assert rag_cache.load_passages() == passages


def test_count_documents_needs_every_word(library):
    assert rag_cache.count_documents(["CLIMATE"]) == (1, {"Climate report.pdf": 1})
    assert rag_cache.count_documents(["the"]) == (
        2,
        {"Climate report.pdf": 1, "Cookbook.pdf": 1},
    )
    assert rag_cache.count_documents(["bread", "climate"]) == (0, {})
    assert rag_cache.count_documents([]) == (0, {})


def test_search_orders_by_meaning_and_drops_weak_hits(library):
    hits = rag_cache.search("sea level", k=3, min_score=0.5)
    assert [(round(s, 1), p["chunk"], p["file"]) for s, p in hits] == [
        (1.0, 0, "Climate report.pdf"),
        (0.8, 1, "Climate report.pdf"),
    ]


def test_empty_cache_finds_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_cache, "SRC", str(tmp_path / "none"))
    monkeypatch.setattr(rag_cache, "OUT", str(tmp_path / "cache"))
    rag_cache._index["sig"] = None
    assert rag_cache.search("anything") == []


# ---------------------------------------------------------------------------- the tool
def test_tool_semantic_mode_marks_text_untrusted(library):
    r = oracle_search.OracleSearchTool().execute(query="sea level", limit=2)
    assert r.success
    assert r.content.startswith(
        "Passages from the ORACLE library:\n\n"
        "[1] Climate report.pdf (chunk 0, relevance 1.00)"
    )
    assert r.content.endswith(oracle_search.UNTRUSTED_NOTE)


def test_tool_keyword_mode_only_counts(library):
    r = oracle_search.OracleSearchTool().execute(query="climate", mode="keyword")
    assert r.content == (
        "Keyword search for 'climate': 1 documents and 1 passages contain it.\n"
        "Top documents:\nClimate report.pdf (1 passages)"
    )


def test_tool_explains_missing_embedding_model(library, monkeypatch):
    def offline(text, timeout=60.0):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(rag_cache, "embed_query", offline)
    r = oracle_search.OracleSearchTool().execute(query="sea level")
    assert not r.success and "Is LM Studio running" in r.content


@pytest.mark.parametrize("raw, limit", [(None, 4), ("x", 4), (0, 1), (99, 8), ("3", 3)])
def test_limit_is_clamped(raw, limit):
    assert oracle_search._limit(raw) == limit


def test_tool_needs_a_query():
    assert (
        oracle_search.OracleSearchTool().execute(query="  ").content
        == "No query provided."
    )
