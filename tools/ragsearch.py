import glob, json, os, sys, time
import numpy as np
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ragcache

OUT = ragcache.OUT
MODEL = "text-embedding-nomic-embed-text-v1.5"


def safe(s, n=400):
    return str(s).encode("ascii", "replace").decode().replace("\n", " ")[:n]


def load():
    vs, meta = [], []
    for npy in sorted(glob.glob(os.path.join(OUT, "shard_*.npy"))):
        jl = npy[:-4] + ".jsonl"
        vs.append(np.load(npy))
        with open(jl, encoding="utf-8") as f:
            meta.extend(json.loads(line) for line in f)
    return np.concatenate(vs), meta


def embed(text):
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request("http://localhost:1234/v1/embeddings", data=body,
                                 headers={"Content-Type": "application/json"})
    e = np.array(json.load(urllib.request.urlopen(req, timeout=120))["data"][0]["embedding"], dtype=np.float32)
    return e / np.linalg.norm(e)


def search(V, meta, query, k=5):
    s = V @ embed(query)
    idx = np.argpartition(-s, min(k, len(s) - 1))[:k]
    idx = idx[np.argsort(-s[idx])]
    return [(float(s[i]), meta[i]) for i in idx]


if __name__ == "__main__":
    t0 = time.time()
    n = ragcache.refresh(verbose=False)
    if n:
        print("refreshed shards:", n)
    V, meta = load()
    print("passages loaded:", len(meta), "in %.1fs" % (time.time() - t0))
    q = " ".join(sys.argv[1:]) or "climate change"
    t1 = time.time()
    for score, m in search(V, meta, q):
        print("%.3f  %s (chunk %s)" % (score, safe(m["f"], 80), m["c"]))
        print("      " + safe(m["t"]))
    print("search took %.2fs" % (time.time() - t1))