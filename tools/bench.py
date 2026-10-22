import json, time, os, urllib.request
H = os.path.expanduser("~/.openjarvis")
LOG = os.path.join(H, "tool-calls.txt")
def post(url, body):
    r = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=300))
def lines():
    try:
        return open(LOG, errors="replace").read().splitlines()
    except OSError:
        return []
model = json.load(urllib.request.urlopen("http://127.0.0.1:8765", timeout=10))["model"]
qs = json.load(open("tools/bench.json"))
res = []
for i, c in enumerate(qs, 1):
    n0 = len(lines())
    try:
        ans = post("http://127.0.0.1:8000/v1/chat/completions", {"model": model, "messages": [{"role": "user", "content": c["q"]}]})["choices"][0]["message"]["content"] or ""
    except Exception as e:
        ans = "ERROR " + str(e)[:80]
    time.sleep(1.5)
    called = sorted({l.split()[1] for l in lines()[n0:] if len(l.split()) > 1})
    tool_ok = (c["tool"] in called) if c["tool"] else (not called)
    exp_ok = (c["expect"].lower() in ans.lower()) if c["expect"] else True
    ok = tool_ok and exp_ok
    res.append({"q": c["q"], "ok": ok, "tool_ok": tool_ok, "expect_ok": exp_ok, "called": called})
    print(i, "PASS" if ok else "FAIL", "tool_ok=%s expect_ok=%s called=%s" % (tool_ok, exp_ok, called))
p = sum(r["ok"] for r in res)
out = {"accuracy": round(100.0 * p / len(res), 1), "passed": p, "total": len(res), "time": time.strftime("%Y-%m-%d %H:%M:%S"), "model": model, "details": res}
json.dump(out, open(os.path.join(H, "bench-result.json"), "w"), indent=1)
print("ACCURACY: %s%% (%d of %d)" % (out["accuracy"], p, len(res)))
