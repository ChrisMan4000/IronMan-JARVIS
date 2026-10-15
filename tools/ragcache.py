"""ragcache: turns the LM Studio Big RAG index (slow JSON shards) into a fast cache (.npy vectors + .jsonl passages).

Used by the oracle_search tool. Reads only C:\\AI\\Big-RAG, writes only C:\\AI\\Big-RAG-cache. Run by hand to rebuild:
  uv run --no-sync python tools\\ragcache.py
Reviewed 2026-10-14: comments added, behavior unchanged. (Data is read from JSON and numpy files only, never executed.)
"""
import glob, json, os, sys
import numpy as np

# Where the Big RAG index is and where the fast cache goes
SRC = r"C:\AI\Big-RAG"
OUT = r"C:\AI\Big-RAG-cache"


# cl: makes text safe to write as UTF-8 (replaces broken characters)
def cl(s):
    return str(s).encode("utf-8", "replace").decode("utf-8")


# sig: file size + change time, to see whether an index.json changed
def sig(p):
    s = os.stat(p)
    return [s.st_size, int(s.st_mtime)]


def refresh(verbose=True):
    """Rebuild the cache for every shard whose index.json changed. Returns the number rebuilt."""
    os.makedirs(OUT, exist_ok=True)
    rebuilt = 0
    for shard in sorted(glob.glob(os.path.join(SRC, "shard_*"))):
        p = os.path.join(shard, "index.json")
        if not os.path.exists(p):
            continue
        name = os.path.basename(shard)
        sp = os.path.join(OUT, name + ".sig.json")
        npy = os.path.join(OUT, name + ".npy")
        jl = os.path.join(OUT, name + ".jsonl")
        cur = sig(p)
        try:
            if os.path.exists(sp) and os.path.exists(npy) and os.path.exists(jl) and json.load(open(sp)) == cur:
                continue
            items = json.load(open(p, encoding="utf-8"))["items"]
            V = np.array([it["vector"] for it in items], dtype=np.float32)
            with open(jl + ".tmp", "w", encoding="utf-8") as mf:
                for it in items:
                    m = it["metadata"]
                    mf.write(json.dumps({"t": cl(m.get("text", "")), "f": cl(m.get("fileName", "")),
                                         "p": cl(m.get("filePath", "")), "c": m.get("chunkIndex", 0)},
                                        ensure_ascii=False) + "\n")
            with open(npy + ".tmp", "wb") as nf:
                np.save(nf, V)
            os.replace(jl + ".tmp", jl)
            os.replace(npy + ".tmp", npy)
            json.dump(cur, open(sp, "w"))
            rebuilt += 1
            if verbose:
                print(name, "rebuilt:", len(items), "passages")
                sys.stdout.flush()
        except Exception as ex:
            if verbose:
                print(name, "skipped (will retry):", str(ex).encode("ascii", "replace").decode()[:100])
    return rebuilt


# Run by hand: rebuild whatever changed
if __name__ == "__main__":
    n = refresh()
    print("DONE, shards rebuilt:", n)