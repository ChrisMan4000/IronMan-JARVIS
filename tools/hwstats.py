"""Jarvis hardware helper (port 8765, this PC only).

Collects CPU / GPU / network / loaded-model stats for the HUD and serves a few
small routes: document links, word counts, model control, Hue and Tado shortcuts.

Security rules (added 2026-10-14):
- Only requests with Host 127.0.0.1:8765 or localhost:8765 are answered
  (blocks DNS-rebinding attacks from websites).
- Routes that CHANGE something or fetch from the internet (/hue, /tado, /news, /m/set, /m/load) only work when the
  request comes from the HUD page (Origin or Referer = http://localhost:5173).
- Other websites cannot READ the answers: the CORS header is only sent to the HUD.
- Model ids are checked against LM Studio's own list before any command is run.
"""
import ctypes, glob, ipaddress, json, mimetypes, os, re, subprocess, threading, time
import urllib.parse, urllib.request
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
LINK_MBPS = 250  # your DSL line speed (250 Mbps)

# ---------------------------------------------------------------- security
ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
ALLOWED_HOSTS = ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)


def host_ok(h):
    """True when the Host header is this helper (stops DNS rebinding)."""
    return h.headers.get("Host", "").strip().lower() in ALLOWED_HOSTS


def trusted_origin(h):
    """Return the HUD origin the request came from, or None.
    If an Origin header exists it must be allowed; otherwise the Referer must be
    the HUD page (exact origin, followed by / or nothing)."""
    o = h.headers.get("Origin", "")
    if o:
        return o if o in ALLOWED_ORIGINS else None
    ref = h.headers.get("Referer", "")
    for a in ALLOWED_ORIGINS:
        if ref == a or ref.startswith(a + "/"):
            return a
    return None


def send(h, code, body, ctype="application/json", extra=None):
    """Send one response. The CORS header is added only for the HUD."""
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("X-Content-Type-Options", "nosniff")
    o = trusted_origin(h)
    if o:
        h.send_header("Access-Control-Allow-Origin", o)
        h.send_header("Vary", "Origin")
    for k, v in (extra or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)


def need_trusted(h):
    """For routes that change something: refuse unless the request is from the HUD."""
    if trusted_origin(h) is None:
        send(h, 403, {"ok": False, "text": "refused: request did not come from the HUD",
                      "error": "forbidden"})
        return False
    return True


def query(h):
    """URL query string as a simple dict (first value of each key)."""
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query).items()}


# ---------------------------------------------------------------- CPU / network / GPU sampling
class FT(ctypes.Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]


def val(x):
    return (x.hi << 32) | x.lo


def cpu_times():
    """(idle, total) CPU time from Windows."""
    i, k, u = FT(), FT(), FT()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
    return val(i), val(k) + val(u)


def net_bytes():
    """(received, sent) bytes since boot, read from 'netstat -e'."""
    out = subprocess.check_output(["netstat", "-e"], text=True, timeout=5)
    for line in out.splitlines():
        m = re.match(r"^\s*\S+\s+(\d+)\s+(\d+)\s*$", line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


# Shared data returned by GET /
stats = {"co2": None, "model": None, "model_gb": None, "conns": [], "cpu_load": 0, "cpu_temp": None, "gpu": None,
         "net": {"down_pct": 0, "up_pct": 0, "down_mbps": 0, "up_mbps": 0, "link_mbps": LINK_MBPS}}


def sampler():
    """Once per second: CPU load, network speed and GPU values (nvidia-smi)."""
    prev = cpu_times()
    pn = net_bytes()
    pt = time.time()
    while True:
        time.sleep(1)
        cur = cpu_times()
        idle, total = cur[0] - prev[0], cur[1] - prev[1]
        prev = cur
        if total > 0:
            stats["cpu_load"] = round(100 * (1 - idle / total), 1)
        try:
            nn, nt = net_bytes(), time.time()
            if nn and pn:
                dt = max(0.1, nt - pt)
                down = max(0, nn[0] - pn[0]) * 8 / dt / 1e6
                up = max(0, nn[1] - pn[1]) * 8 / dt / 1e6
                stats["net"] = {"down_pct": round(min(100, 100 * down / LINK_MBPS), 2),
                                "up_pct": round(min(100, 100 * up / LINK_MBPS), 2),
                                "down_mbps": round(down, 2), "up_mbps": round(up, 2),
                                "link_mbps": LINK_MBPS}
            pn, pt = nn, nt
        except Exception:
            pass
        try:
            out = subprocess.check_output(
                ["nvidia-smi",
                 "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw,fan.speed",
                 "--format=csv,noheader,nounits"], text=True, timeout=5).strip()
            n, u, t, mu, mt, p, f = [s.strip() for s in out.split(",")]
            fan = float(f) if f[:1].isdigit() else None
            stats["gpu"] = {"name": n, "load": float(u), "temp": float(t),
                            "mem_used": float(mu), "mem_total": float(mt), "power": float(p), "fan": fan}
        except Exception:
            stats["gpu"] = None


# ---------------------------------------------------------------- connections + offline location (world map)
geo = {}

try:
    import maxminddb
    _rd = maxminddb.open_database(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dbip.mmdb"))
except Exception:
    _rd = None  # no location database: the map simply shows no connections


def conn_ips():
    """Public IPs with established TCP connections, with a count each."""
    out = subprocess.check_output(["netstat", "-n", "-p", "tcp"], text=True, timeout=8)
    ips = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 4 and p[0] == "TCP" and p[3] == "ESTABLISHED":
            ip = p[2].rsplit(":", 1)[0].strip("[]")
            try:
                a = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if a.is_private or a.is_loopback or a.is_link_local or a.is_multicast:
                continue
            ips[ip] = ips.get(ip, 0) + 1
    return ips


def geo_lookup(ips):
    """Locate IPs with the offline database dbip.mmdb (no data leaves this PC)."""
    for ip in ips:
        try:
            r = (_rd.get(ip) if _rd else None) or {}
            loc = r.get("location") or {}
            if "latitude" in loc and "longitude" in loc:
                geo[ip] = {"lat": loc["latitude"], "lon": loc["longitude"],
                           "country": (r.get("country") or {}).get("names", {}).get("en", ""),
                           "city": (r.get("city") or {}).get("names", {}).get("en", ""),
                           "org": ""}
            else:
                geo[ip] = {"bad": 1}
        except Exception:
            geo[ip] = {"bad": 1}


def conn_loop():
    """Every 5 seconds: refresh the connection list for the map."""
    while True:
        try:
            ips = conn_ips()
            new = [i for i in ips if i not in geo]
            if new:
                geo_lookup(new)
            stats["conns"] = [
                {"ip": i, "n": n, "lat": geo[i]["lat"], "lon": geo[i]["lon"],
                 "country": geo[i].get("country", ""), "city": geo[i].get("city", ""),
                 "org": geo[i].get("org", "")}
                for i, n in ips.items() if i in geo and "lat" in geo[i]]
        except Exception:
            pass
        time.sleep(5)


threading.Thread(target=conn_loop, daemon=True).start()

# ---------------------------------------------------------------- loaded model (LM Studio)
_size_cache = {"id": None, "gb": None, "t": 0}


def model_size_gb(mid):
    """Size of the loaded model in GB from 'lms ps --json' (cached per model)."""
    if not mid:
        return None
    if _size_cache["id"] == mid and _size_cache["gb"] is not None:
        return _size_cache["gb"]
    if _size_cache["id"] == mid and time.time() - _size_cache["t"] < 30:
        return None
    _size_cache["id"] = mid
    _size_cache["t"] = time.time()
    _size_cache["gb"] = None
    try:
        out = subprocess.run(["lms", "ps", "--json"], capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout
        for m in json.loads(out):
            if m.get("identifier") == mid or m.get("modelKey") == mid:
                _size_cache["gb"] = round(m["sizeBytes"] / 1e9, 1)
    except Exception:
        pass
    return _size_cache["gb"]


def model_loop():
    """Every 3 seconds: which LLM is loaded in LM Studio, and its size."""
    while True:
        try:
            req = urllib.request.Request("http://localhost:1234/api/v0/models")
            data = json.load(urllib.request.urlopen(req, timeout=4)).get("data", [])
            loaded = [m["id"] for m in data
                      if m.get("state") == "loaded" and m.get("type") in ("llm", "vlm")]
            stats["model"] = loaded[0] if loaded else None
            stats["model_gb"] = model_size_gb(stats["model"])
        except Exception:
            stats["model"] = None
        time.sleep(3)


threading.Thread(target=model_loop, daemon=True).start()


# ---------------------------------------------------------------- CO2 value (NOAA)
def co2_loop():
    """Latest weekly CO2 value from NOAA Mauna Loa, refreshed every 6 hours."""
    urls = ["https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_weekly_mlo.txt",
            "https://gml.noaa.gov/aftp/products/trends/co2/co2_weekly_mlo.txt"]
    while True:
        ok = False
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "jarvis-hud"})
                txt = urllib.request.urlopen(req, timeout=15).read().decode()
                last = None
                for line in txt.splitlines():
                    p = line.split()
                    if line.startswith("#") or len(p) < 5:
                        continue
                    v = float(p[4])
                    if v > 0:
                        last = (v, "%s-%02d-%02d" % (p[0], int(p[1]), int(p[2])))
                if last:
                    stats["co2"] = {"ppm": last[0], "date": last[1]}
                    ok = True
                    break
            except Exception:
                pass
        time.sleep(6 * 3600 if ok else 600)


threading.Thread(target=co2_loop, daemon=True).start()


def tools_loop():
    """Every second: when web_search / oracle_search last ran (for the two HUD lights)."""
    d = os.path.join(os.path.expanduser("~"), ".openjarvis")
    while True:
        r = {"now": time.time()}
        for k, f in (("web", "tool-web_search.txt"), ("doc", "tool-oracle_search.txt")):
            try:
                with open(os.path.join(d, f)) as fh:
                    r[k] = float(fh.read().strip())
            except Exception:
                r[k] = 0
        stats["tools"] = r
        time.sleep(1)


threading.Thread(target=tools_loop, daemon=True).start()

# ---------------------------------------------------------------- documents (ORACLE library): /doc, /docexists
DOC_ROOT = os.environ.get("JARVIS_DOC_ROOT") or os.path.join(os.path.expanduser("~"), "Documents", "ORACLE")  # folder for document search
_doc_idx = {"t": 0, "map": {}}
# File types that could run scripts in the browser: shown as plain text instead.
ACTIVE_TYPES = {"text/html", "application/xhtml+xml", "image/svg+xml", "text/xml",
                "application/xml", "application/javascript", "text/javascript"}


def _doc_map():
    """Lower-case file name -> full path for every file in the ORACLE folder (refreshed every 10 min)."""
    if time.time() - _doc_idx["t"] > 600:
        m = {}
        for root, _, files in os.walk(DOC_ROOT):
            for f in files:
                m.setdefault(f.lower(), os.path.join(root, f))
        _doc_idx.update(t=time.time(), map=m)
    return _doc_idx["map"]


def inside_root(path):
    """True only when the real path (links resolved) is inside the ORACLE folder."""
    try:
        root = os.path.normcase(os.path.realpath(DOC_ROOT))
        p = os.path.normcase(os.path.realpath(path))
        return os.path.commonpath([root, p]) == root
    except ValueError:
        return False


def find_doc(name):
    """Full path of a document by file name (exact, else unique partial match), or None."""
    name = (name or "").strip().lower()
    if not name:
        return None
    m = _doc_map()
    path = m.get(name)
    if not path:
        hits = [p for k, p in m.items() if name in k or k in name]
        path = hits[0] if len(hits) == 1 else None
    return path if path and inside_root(path) else None


def serve_docexists(h):
    """/docexists?f=<file> -> {"exists": true/false}"""
    send(h, 200, {"exists": bool(find_doc(query(h).get("f", "")))})


def serve_doc(h):
    """/doc?f=<file> -> the document itself (only from inside the ORACLE folder)."""
    path = find_doc(query(h).get("f", ""))
    if not path:
        return send(h, 404, b"not found", "text/plain")
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if ctype.split(";")[0] in ACTIVE_TYPES:
        ctype = "text/plain; charset=utf-8"
    with open(path, "rb") as fh:
        data = fh.read()
    fname = os.path.basename(path).encode("ascii", "replace").decode().replace('"', "'")
    send(h, 200, data, ctype, {"Content-Disposition": 'inline; filename="%s"' % fname})


# ---------------------------------------------------------------- word counts: /count
_cnt = {"sig": None, "rows": [], "checked": 0.0}


def _load_texts():
    """All document passages from the Big-RAG cache (rebuilt at most every 10 minutes)."""
    if time.time() - _cnt["checked"] > 600:
        try:
            import ragcache
            ragcache.refresh(verbose=False)
        except Exception:
            pass
        _cnt["checked"] = time.time()
    files = sorted(glob.glob(os.path.join(r"C:\AI\Big-RAG-cache", "shard_*.jsonl")))
    sig = tuple((f, os.stat(f).st_mtime) for f in files)
    if sig != _cnt["sig"]:
        rows = []
        for f in files:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    m = json.loads(line)
                    rows.append((m["f"], m["t"].lower()))
        _cnt.update(sig=sig, rows=rows)
    return _cnt["rows"]


def count_word(word):
    """How many documents / passages contain the word, plus the top 15 documents."""
    w = word.lower()
    files = {}
    n = 0
    for f, t in _load_texts():
        if w in t:
            n += 1
            files[f] = files.get(f, 0) + 1
    top = sorted(files.items(), key=lambda kv: -kv[1])[:15]
    return {"word": word, "documents": len(files), "passages": n,
            "top": [{"f": f, "n": c} for f, c in top]}


def serve_count(h):
    """/count?w=<word> -> JSON with the counts."""
    w = query(h).get("w", "").strip()[:60]
    send(h, 200, count_word(w) if w else {"error": "no word"})


# ---------------------------------------------------------------- model control: /m/list, /m/set, /m/load
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".openjarvis", "hud-model-settings.json")
SET_DEFAULTS = {"reasoning": False, "thinking": False, "context": 8192}
_set_lock = threading.Lock()
_load_state = {"loading": None, "error": None}


def read_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def get_setting(model):
    d = dict(SET_DEFAULTS)
    d.update(read_settings().get(model, {}))
    return d


def put_setting(model, **kw):
    """Save per-model settings (reasoning, thinking, context) atomically."""
    with _set_lock:
        allm = read_settings()
        cur = dict(SET_DEFAULTS)
        cur.update(allm.get(model, {}))
        cur.update(kw)
        allm[model] = cur
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(allm, fh, indent=2)
        os.replace(tmp, SETTINGS_PATH)
        return cur


def list_models():
    """All LLMs known to LM Studio with state, context and saved settings."""
    data = json.load(urllib.request.urlopen("http://localhost:1234/api/v0/models", timeout=5)).get("data", [])
    out = []
    for m in data:
        if m.get("type") not in ("llm", "vlm"):
            continue
        row = {"id": m["id"], "state": m.get("state"), "max": m.get("max_context_length"),
               "loaded_ctx": m.get("loaded_context_length")}
        row.update(get_setting(m["id"]))
        _c = read_caps().get(m["id"])
        row["caps"] = ({"reasoning": _c["reasoning"], "thinking": _c["thinking"]} if _c else None)
        row["probing"] = (_probing["model"] == m["id"])
        out.append(row)
    return out


def _do_load(mid, ctx):
    """Unload everything, then load one model with the saved context (runs in a thread)."""
    _load_state.update(loading=mid, error=None)
    try:
        subprocess.run(["lms", "unload", "--all"], timeout=60, capture_output=True)
        r = subprocess.run(["lms", "load", mid, "-c", str(ctx), "-y"], timeout=300, capture_output=True, text=True)
        if r.returncode != 0:
            _load_state["error"] = ((r.stderr or "") + (r.stdout or ""))[-200:] or "load failed"
    except Exception as e:
        _load_state["error"] = str(e)[:200]
    _load_state["loading"] = None


def serve_model_api(h):
    """/m/list (read), /m/set and /m/load (only from the HUD, only for models LM Studio knows)."""
    u = urllib.parse.urlparse(h.path)
    q = query(h)
    op = u.path[len("/m/"):]
    if op in ("set", "load") and not need_trusted(h):
        return
    try:
        if op == "list":
            res = {"models": list_models(), "loading": _load_state["loading"], "error": _load_state["error"]}
        elif op in ("set", "load"):
            mid = q.get("model", "")
            if mid not in {m["id"] for m in list_models()}:
                res = {"error": "unknown model"}
            elif op == "set":
                kw = {}
                if "reasoning" in q:
                    kw["reasoning"] = q["reasoning"] == "1"
                if "thinking" in q:
                    kw["thinking"] = q["thinking"] == "1"
                if "context" in q:
                    kw["context"] = max(1024, min(int(q["context"]), 1048576))
                res = put_setting(mid, **kw)
            elif _load_state["loading"]:
                res = {"error": "busy"}
            else:
                ctx = get_setting(mid)["context"]
                threading.Thread(target=_do_load, args=(mid, ctx), daemon=True).start()
                res = {"loading": mid, "context": ctx}
        else:
            res = {"error": "unknown"}
    except Exception as e:
        res = {"error": str(e)[:200]}
    send(h, 200, res)


# ---------------------------------------------------------------- capability check (does a model support reasoning / thinking?)
CAPS_PATH = os.path.join(os.path.expanduser("~"), ".openjarvis", "hud-model-caps.json")
_caps_lock = threading.Lock()
_probing = {"model": None}


def read_caps():
    try:
        with open(CAPS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _probe_call(model, extra):
    """One tiny test question to LM Studio; returns (tokens, has_reasoning_text)."""
    body = {"model": model, "temperature": 0, "max_tokens": 400,
            "messages": [{"role": "user", "content": "What is 17 times 23? Answer with the number only."}]}
    body.update(extra)
    req = urllib.request.Request("http://localhost:1234/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    j = json.load(urllib.request.urlopen(req, timeout=120))
    msg = j["choices"][0]["message"]
    toks = int((j.get("usage") or {}).get("completion_tokens", 0))
    has = bool((msg.get("reasoning_content") or msg.get("reasoning") or "").strip()) or "<think>" in (msg.get("content") or "")
    return toks, has


def _differs(a, b):
    return a[1] != b[1] or max(a[0], b[0]) >= 1.5 * max(1, min(a[0], b[0]))


def probe_model(model):
    """Test the four switches and save the result in hud-model-caps.json."""
    _probing["model"] = model
    try:
        r_off = _probe_call(model, {"reasoning_effort": "none"})
        r_on = _probe_call(model, {"reasoning_effort": "medium"})
        t_off = _probe_call(model, {"chat_template_kwargs": {"enable_thinking": False}})
        t_on = _probe_call(model, {"chat_template_kwargs": {"enable_thinking": True}})
        res = {"reasoning": _differs(r_off, r_on), "thinking": _differs(t_off, t_on),
               "detail": {"r_off": list(r_off), "r_on": list(r_on), "t_off": list(t_off), "t_on": list(t_on)}}
        with _caps_lock:
            allc = read_caps()
            allc[model] = res
            tmp = CAPS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(allc, fh, indent=2)
            os.replace(tmp, CAPS_PATH)
    except Exception:
        pass
    _probing["model"] = None


_failed = {}


def caps_loop():
    """Test every newly loaded model once (retry a failed test after 5 minutes)."""
    time.sleep(5)
    while True:
        try:
            m = stats.get("model")
            if m and m not in read_caps() and not _probing["model"] and time.time() - _failed.get(m, 0) > 300:
                probe_model(m)
                if m not in read_caps():
                    _failed[m] = time.time()
        except Exception:
            pass
        time.sleep(5)


threading.Thread(target=caps_loop, daemon=True).start()


# ---------------------------------------------------------------- smart-home shortcuts: /hue, /tado (only from the HUD)
def serve_hue(h):
    """/hue?room=<text>&state=on|off -> switches a Hue room (same code as the hue_set tool)."""
    if not need_trusted(h):
        return
    q = query(h)
    try:
        from openjarvis.tools.hue_set import HueSetTool
        r = HueSetTool().execute(room=q.get("room", "")[:60], state=q.get("state", "")[:5])
        out = {"ok": bool(r.success), "text": str(r.content)}
    except Exception as e:
        out = {"ok": False, "text": "hue error: " + type(e).__name__}
    send(h, 200, out)


def serve_tado(h):
    """/tado?action=resume|off&room=<name> -> Tado heating (other actions are refused)."""
    if not need_trusted(h):
        return
    q = query(h)
    if q.get("action", "") not in ("resume", "off"):
        out = {"ok": False, "text": "refused: only resume and off are allowed here"}
    else:
        try:
            from openjarvis.tools.tado_heating import TadoHeatingTool
            r = TadoHeatingTool().execute(action=q.get("action", ""), room=q.get("room", "")[:60])
            out = {"ok": bool(r.success), "text": str(r.content)}
        except Exception as ex:
            out = {"ok": False, "text": "tado error: " + type(ex).__name__}
    send(h, 200, out)


def serve_news(h):
    """/news?feed=<short name>&limit=<1-10> -> headlines from the rss_news tool (HUD shortcut, no model involved).
    Only the built-in short feed names are accepted (no custom addresses here)."""
    if not need_trusted(h):
        return
    q = query(h)
    try:
        from openjarvis.tools.rss_news import FEEDS, RssNewsTool
        feed = q.get("feed", "")
        if feed not in FEEDS:
            out = {"ok": False, "text": "unknown feed name"}
        else:
            try:
                limit = max(1, min(10, int(q.get("limit", "5"))))
            except ValueError:
                limit = 5
            r = RssNewsTool().execute(feed=feed, limit=limit)
            out = {"ok": bool(r.success), "text": str(r.content)}
    except Exception as e:
        out = {"ok": False, "text": "news error: " + type(e).__name__}
    send(h, 200, out)


# ---------------------------------------------------------------- HTTP server
# Fan speeds from LibreHardwareMonitor (local web server, port 8085). Read-only, fixed local address.
def _walk_fans(node, out):
    v = str(node.get("Value", ""))
    if v.endswith("RPM"):
        m = re.match(r"[\d.,]+", v)
        if m:
            out.append({"name": str(node.get("Text", ""))[:40], "rpm": int(float(m.group(0).replace(",", ".")))})
    for c in node.get("Children", []) or []:
        _walk_fans(c, out)


def fans_loop():
    while True:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8085/data.json", timeout=3) as r:
                out = []
                _walk_fans(json.loads(r.read().decode("utf-8")), out)
                stats["fans"] = [f for f in out if not f["name"].startswith("GPU Fan")]
        except Exception:
            stats["fans"] = None
        time.sleep(2)


threading.Thread(target=fans_loop, daemon=True).start()
def bench_loop():
    """Reads bench-result.json (written by tools\bench.py) every 10 s into stats["bench"]."""
    import os as _os
    p = _os.path.join(_os.path.expanduser("~"), ".openjarvis", "bench-result.json")
    while True:
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            stats["bench"] = {"accuracy": d.get("accuracy"), "passed": d.get("passed"), "total": d.get("total"), "time": d.get("time")}
        except Exception:
            stats["bench"] = None
        time.sleep(10)
threading.Thread(target=bench_loop, daemon=True).start()


class H(BaseHTTPRequestHandler):
    """Routes GET requests. Anything with a wrong Host header is refused first."""

    def do_GET(self):
        if not host_ok(self):
            return send(self, 403, {"error": "bad host"})
        path = urllib.parse.urlparse(self.path).path
        if path == "/tado":
            return serve_tado(self)
        if path == "/hue":
            return serve_hue(self)
        if path == "/news":
            return serve_news(self)
        if path.startswith("/m/"):
            return serve_model_api(self)
        if path == "/count":
            return serve_count(self)
        if path == "/docexists":
            return serve_docexists(self)
        if path == "/doc":
            return serve_doc(self)
        if path == "/":
            return send(self, 200, stats)
        send(self, 404, {"error": "not found"})

    def log_message(self, *a):
        pass


threading.Thread(target=sampler, daemon=True).start()
print("Hardware stats on http://127.0.0.1:%d" % PORT)
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
