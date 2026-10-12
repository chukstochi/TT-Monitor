import os, json, time, ssl, socket, threading, requests, pymysql, pymysql.cursors
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from functools import wraps
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, jsonify, session, send_from_directory, redirect

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "frontend", "dist")
app = Flask(__name__, static_folder=DIST, static_url_path="")
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
PROJECTS = json.load(open(os.path.join(HERE, "projects.json"), encoding="utf-8"))
INTERVAL = int(os.getenv("CHECK_EVERY_SEC", 60))

_u = urlparse(os.getenv("MYSQL_URL", ""))
CFG = dict(host=_u.hostname or os.getenv("MYSQL_HOST", "127.0.0.1"), port=_u.port or int(os.getenv("MYSQL_PORT", "3306")),
           user=unquote(_u.username) if _u.username else os.getenv("MYSQL_USER", "root"),
           password=unquote(_u.password) if _u.password else os.getenv("MYSQL_PASSWORD", ""))
DB = _u.path.lstrip("/") or os.getenv("MYSQL_DB", "monitor")

def conn(use_db=True):
    return pymysql.connect(**CFG, database=DB if use_db else None, charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor, autocommit=True)

def q(sql, args=(), one=False, write=False):
    c = conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, args)
            if write: return cur.lastrowid
            rows = [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in cur.fetchall()]
            return (rows[0] if rows else None) if one else rows
    finally:
        c.close()

def init():
    c = conn(False)
    with c.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB}` CHARACTER SET utf8mb4")
    c.close()
    q("""CREATE TABLE IF NOT EXISTS checks(
        id BIGINT AUTO_INCREMENT PRIMARY KEY, project VARCHAR(40), ok TINYINT, code INT, ms INT,
        error VARCHAR(200), ts BIGINT, INDEX idx_pt (project, ts)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""", write=True)
    q("""CREATE TABLE IF NOT EXISTS events(
        id BIGINT AUTO_INCREMENT PRIMARY KEY, project VARCHAR(40), type VARCHAR(12), vid VARCHAR(40),
        label VARCHAR(200), ts BIGINT, INDEX idx_ev (project, type, ts)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""", write=True)

# ---------- monitoring ----------
def check_one(p):
    t0, code, err, ok = time.time(), None, None, False
    try:
        r = requests.get(p["url"].rstrip("/") + p.get("path", ""), timeout=15, headers={"User-Agent": "TT-Monitor/1.0"})
        code, ok = r.status_code, r.status_code < 400
        if not ok: err = f"HTTP {code}"
        elif p.get("expect") and p["expect"] not in r.text: ok, err = False, "expected text not found"
    except Exception as ex:
        err = str(ex)[:180]
    return ok, code, int((time.time() - t0) * 1000), err

def alert(p, ok, err):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat): return
    msg = f"✅ {p['name']} is back up" if ok else f"🔴 {p['name']} is DOWN: {err}"
    try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": msg}, timeout=10)
    except Exception: pass

ssl_info = {}  # project key -> {"days":, "expires":, "checked":, "error":, "alert_day":}

def notify(msg):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat): return
    try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": msg}, timeout=10)
    except Exception: pass

def check_ssl(p):
    u = urlparse(p["url"])
    if u.scheme != "https": return
    info = ssl_info.setdefault(p["key"], {})
    if time.time() - info.get("checked", 0) < 6 * 3600: return
    info["checked"] = time.time()
    try:
        with socket.create_connection((u.hostname, u.port or 443), timeout=8) as sk:
            with ssl.create_default_context().wrap_socket(sk, server_hostname=u.hostname) as ss:
                exp = ssl.cert_time_to_seconds(ss.getpeercert()["notAfter"])
        info.update(days=int((exp - time.time()) // 86400), expires=int(exp), error=None)
        day = time.strftime("%Y-%m-%d")
        if info["days"] <= 14 and info.get("alert_day") != day:
            info["alert_day"] = day
            notify(f"⚠️ {p['name']}: SSL certificate expires in {info['days']} days")
    except Exception as ex:
        info.update(days=None, error=str(ex)[:120])

state = {}  # project key -> consecutive failures / alerted
lock = threading.Lock()

def run_checks():
    if not lock.acquire(blocking=False): return
    try:
        with ThreadPoolExecutor(max_workers=len(PROJECTS)) as ex:
            results = list(ex.map(check_one, PROJECTS))
        now = int(time.time())
        for p, (ok, code, ms, err) in zip(PROJECTS, results):
            q("INSERT INTO checks(project,ok,code,ms,error,ts) VALUES(%s,%s,%s,%s,%s,%s)", (p["key"], int(ok), code, ms, err, now), write=True)
            check_ssl(p)
            s = state.setdefault(p["key"], {"fails": 0, "down": False})
            if ok:
                if s["down"]: alert(p, True, None)
                s["fails"], s["down"] = 0, False
            else:
                s["fails"] += 1
                if s["fails"] == 2 and not s["down"]:  # two failures in a row = real outage, not a blip
                    s["down"] = True; alert(p, False, err)
        q("DELETE FROM checks WHERE ts < %s", (now - 91 * 86400,), write=True)
        q("DELETE FROM events WHERE ts < %s", (now - 90 * 86400,), write=True)
    finally:
        lock.release()

def loop():
    while True:
        try: run_checks()
        except Exception as ex: print("[monitor] error:", ex)
        time.sleep(INTERVAL)

init()
if os.getenv("DISABLE_MONITOR") != "1":
    threading.Thread(target=loop, daemon=True).start()

# ---------- api ----------
def need_login(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("ok"): return jsonify(error="Not signed in"), 401
        return f(*a, **k)
    return w

@app.post("/api/login")
def login():
    pw = os.getenv("DASH_PASSWORD")
    if not pw or (request.json or {}).get("password") != pw: return jsonify(error="Wrong password"), 401
    session["ok"] = True; return jsonify(ok=1)

@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=1)

@app.get("/api/me")
@need_login
def me(): return jsonify(ok=1)

@app.get("/api/status")
@need_login
def status():
    since, out = int(time.time()) - 86400, []
    for p in PROJECTS:
        k = p["key"]
        agg = q("SELECT COUNT(*) n, SUM(ok) up, AVG(ms) avg FROM checks WHERE project=%s AND ts>%s", (k, since), one=True)
        last = q("SELECT ok,code,ms,error,ts FROM checks WHERE project=%s ORDER BY ts DESC LIMIT 1", (k,), one=True)
        down = q("SELECT ts,error FROM checks WHERE project=%s AND ok=0 ORDER BY ts DESC LIMIT 1", (k,), one=True)
        n = int(agg["n"] or 0)
        out.append({"key": k, "name": p["name"], "url": p["url"], "latest": last,
                    "uptime": round(100 * (agg["up"] or 0) / n, 2) if n else None,
                    "avg_ms": int(agg["avg"]) if agg["avg"] else None, "last_down": down,
                    "ssl": ssl_info.get(k)})
    return jsonify(projects=out, interval=INTERVAL)

@app.get("/api/history/<key>")
@need_login
def history(key):
    hours = min(int(request.args.get("hours", 24)), 720)
    return jsonify(q("SELECT ts,ok,ms FROM checks WHERE project=%s AND ts>%s ORDER BY ts", (key, int(time.time()) - hours * 3600)))

@app.post("/api/check-now")
@need_login
def check_now(): run_checks(); return jsonify(ok=1)


# ---------- usage tracking ----------
KEYS = {p["key"] for p in PROJECTS}
TYPES = {"view", "click", "download", "install"}
WINDOWS = {"20m": 1200, "1h": 3600, "7d": 7 * 86400, "30d": 30 * 86400}
hits = {}

@app.route("/api/track", methods=["POST", "OPTIONS"])
def track():
    if request.method == "OPTIONS": return "", 204
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    m = int(time.time() // 60)
    h = hits.get(ip)
    if not h or h[0] != m: h = hits[ip] = [m, 0]
    h[1] += 1
    if h[1] > 300: return "", 429
    if len(hits) > 5000: hits.clear()
    d = request.get_json(force=True, silent=True) or {}
    if d.get("project") not in KEYS or d.get("type") not in TYPES: return "", 400
    q("INSERT INTO events(project,type,vid,label,ts) VALUES(%s,%s,%s,%s,%s)",
      (d["project"], d["type"], str(d.get("vid", ""))[:40], str(d.get("label", ""))[:200], int(time.time())), write=True)
    return "", 204

@app.after_request
def cors(r):
    if request.path.startswith(("/api/track", "/t.js")):
        r.headers["Access-Control-Allow-Origin"] = "*"; r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r

@app.get("/t.js")
def tracker(): return send_from_directory(HERE, "tracker.js", mimetype="application/javascript")

# Counted download links: https://YOUR-MONITOR/d/<project>/<name>  (name must be listed in projects.json)
@app.get("/d/<key>/<name>")
def download(key, name):
    p = next((x for x in PROJECTS if x["key"] == key), None)
    url = p and p.get("downloads", {}).get(name)
    if not url: return "Not found", 404
    q("INSERT INTO events(project,type,vid,label,ts) VALUES(%s,%s,%s,%s,%s)", (key, "download", "", name, int(time.time())), write=True)
    return redirect(url)

@app.get("/api/usage")
@need_login
def usage():
    now, out = int(time.time()), []
    for p in PROJECTS:
        k, w = p["key"], {}
        for name, secs in WINDOWS.items():
            rows = q("SELECT type, COUNT(*) n, COUNT(DISTINCT vid) u FROM events WHERE project=%s AND ts>%s GROUP BY type", (k, now - secs))
            r = {x["type"]: x for x in rows}
            g = lambda t, f="n": int(r[t][f]) if t in r else 0
            w[name] = {"visitors": g("view", "u"), "views": g("view"), "clicks": g("click"),
                       "downloads": g("download"), "installs": g("install")}
        top = {t: q("SELECT label, COUNT(*) n FROM events WHERE project=%s AND type=%s AND ts>%s GROUP BY label ORDER BY n DESC LIMIT 5",
                    (k, t, now - 7 * 86400)) for t in ("click", "download")}
        out.append({"key": k, "name": p["name"], "windows": w, "top": top})
    return jsonify(projects=out)


# ---------- incidents, timeline, live ----------
@app.get("/api/incidents")
@need_login
def incidents():
    out, now = [], int(time.time())
    for p in PROJECTS:
        rows = q("SELECT ts, ok, error FROM checks WHERE project=%s AND ts>%s ORDER BY ts", (p["key"], now - 30 * 86400))
        cur = None
        for r in rows:
            if not r["ok"] and cur is None:
                cur = {"project": p["name"], "start": r["ts"], "error": r["error"]}
            elif r["ok"] and cur is not None:
                cur.update(end=r["ts"], ongoing=False); out.append(cur); cur = None
        if cur is not None:
            cur.update(end=None, ongoing=True); out.append(cur)
    for i in out:
        i["duration"] = max(INTERVAL, (i["end"] or now) - i["start"])
    out.sort(key=lambda i: i["start"], reverse=True)
    return jsonify(out[:100])

RANGES = {"24h": (86400, 3600), "7d": (7 * 86400, 86400), "30d": (30 * 86400, 86400)}

@app.get("/api/timeline")
@need_login
def timeline():
    span, step = RANGES.get(request.args.get("range", "24h"), RANGES["24h"])
    now = int(time.time()); start = (now - span) // step * step; n = (now - start) // step + 1
    rows = q("SELECT project, type, (ts-%s) DIV %s AS i, COUNT(*) n, COUNT(DISTINCT vid) u FROM events WHERE ts>=%s GROUP BY project, type, i",
             (start, step, start))
    series = {p["key"]: {m: [0] * n for m in ("visitors", "views", "clicks", "downloads", "installs")} for p in PROJECTS}
    for r in rows:
        sr, i, t = series.get(r["project"]), int(r["i"]), r["type"]
        if not sr or not 0 <= i < n: continue
        if t == "view": sr["visitors"][i], sr["views"][i] = int(r["u"]), int(r["n"])
        elif t == "click": sr["clicks"][i] = int(r["n"])
        elif t == "download": sr["downloads"][i] = int(r["n"])
        elif t == "install": sr["installs"][i] = int(r["n"])
    def uniq(a, b):
        return {r["project"]: int(r["u"]) for r in q(
            "SELECT project, COUNT(DISTINCT vid) u FROM events WHERE type='view' AND ts>=%s AND ts<%s GROUP BY project", (a, b))}
    cur, prev = uniq(start, now + 1), uniq(start - span, start)
    return jsonify(step=step, start=start, projects=[
        {"key": p["key"], "name": p["name"], "series": series[p["key"]],
         "visitors_now": cur.get(p["key"], 0), "visitors_prev": prev.get(p["key"], 0)} for p in PROJECTS])

@app.get("/api/live")
@need_login
def live():
    rows = q("SELECT project, COUNT(DISTINCT vid) u FROM events WHERE type IN ('view','click') AND ts>%s GROUP BY project", (int(time.time()) - 300,))
    by = {r["project"]: int(r["u"]) for r in rows}
    return jsonify(by=by, total=sum(by.values()))


# ---------- public status page (no login; shows only name, status, uptime, incident times) ----------
pub = {"t": 0, "data": None}

@app.get("/status")
def status_page(): return send_from_directory(HERE, "status.html")

@app.get("/api/public/status")
def public_status():
    if pub["data"] and time.time() - pub["t"] < 60: return jsonify(pub["data"])
    now = int(time.time()); days = 90; first = now // 86400 - (days - 1)
    services, incs = [], []
    for p in PROJECTS:
        if not p.get("public"): continue
        k = p["key"]
        by = {int(r["d"]): r for r in q("SELECT ts DIV 86400 AS d, COUNT(*) n, SUM(ok) up FROM checks WHERE project=%s AND ts>=%s GROUP BY d", (k, first * 86400))}
        bars, tn, tu = [], 0, 0
        for d in range(first, first + days):
            r = by.get(d)
            if r and r["n"]:
                n, u = int(r["n"]), int(r["up"] or 0); tn += n; tu += u
                bars.append({"d": d * 86400, "up": round(100 * u / n, 2)})
            else:
                bars.append({"d": d * 86400, "up": None})
        last = q("SELECT ok FROM checks WHERE project=%s ORDER BY ts DESC LIMIT 2", (k,))
        st = "unknown" if not last else "operational" if last[0]["ok"] else ("outage" if len(last) > 1 and not last[1]["ok"] else "degraded")
        services.append({"name": p["name"], "status": st, "uptime": round(100 * tu / tn, 2) if tn else None, "bars": bars})
        cur = None
        for r in q("SELECT ts, ok FROM checks WHERE project=%s AND ts>%s ORDER BY ts", (k, now - 14 * 86400)):
            if not r["ok"] and cur is None: cur = {"service": p["name"], "start": r["ts"]}
            elif r["ok"] and cur is not None: cur.update(end=r["ts"], ongoing=False); incs.append(cur); cur = None
        if cur is not None: cur.update(end=None, ongoing=True); incs.append(cur)
    for i in incs: i["duration"] = max(INTERVAL, (i["end"] or now) - i["start"])
    incs.sort(key=lambda i: i["start"], reverse=True)
    sts = [x["status"] for x in services]
    overall = "none" if not sts else "outage" if "outage" in sts else "degraded" if "degraded" in sts else "operational"
    pub["data"] = {"title": os.getenv("STATUS_TITLE", "TT Status"), "overall": overall, "services": services,
                   "incidents": [{k: v for k, v in i.items() if k != "end"} for i in incs[:20]]}
    pub["t"] = time.time()
    return jsonify(pub["data"])

@app.route("/")
def index(): return send_from_directory(DIST, "index.html")

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5000)), debug=False, threaded=True)
