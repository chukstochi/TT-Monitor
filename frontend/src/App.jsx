import React, { useEffect, useState, useCallback } from "react";
import Usage from "./Usage.jsx";
import Incidents from "./Incidents.jsx";

async function api(path, body) {
  const r = await fetch("/api/" + path, {
    method: body ? "POST" : "GET", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined
  });
  if (r.status === 401) throw new Error("401");
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "Request failed");
  return d;
}
const ago = (ts) => {
  if (!ts) return "never"; const s = Math.floor(Date.now() / 1000 - ts);
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago`;
};

function Chart({ pts }) {
  if (!pts.length) return <p className="mut">No data yet — checks run every minute.</p>;
  const W = 800, H = 160, max = Math.max(100, ...pts.map((p) => p.ms));
  const t0 = pts[0].ts, span = Math.max(1, pts[pts.length - 1].ts - t0);
  const x = (t) => ((t - t0) / span) * W, y = (ms) => H - (ms / max) * (H - 12) - 2;
  const line = pts.filter((p) => p.ok).map((p) => `${x(p.ts).toFixed(1)},${y(p.ms).toFixed(1)}`).join(" ");
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" preserveAspectRatio="none">
        <polyline points={line} fill="none" stroke="#f97316" strokeWidth="2" />
        {pts.filter((p) => !p.ok).map((p) => <line key={p.ts} x1={x(p.ts)} x2={x(p.ts)} y1="0" y2={H} stroke="#ef4444" strokeWidth="2" />)}
      </svg>
      <p className="mut">Response time (max {max} ms). Red lines mark failed checks.</p>
    </>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(null);
  const [pw, setPw] = useState(""); const [err, setErr] = useState("");
  const [data, setData] = useState(null); const [sel, setSel] = useState(() => localStorage.getItem("tt_sel") || null);
  useEffect(() => { if (sel) localStorage.setItem("tt_sel", sel); }, [sel]);
  const [hours, setHours] = useState(24); const [hist, setHist] = useState([]); const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState(() => localStorage.getItem("tt_tab") || "uptime");
  useEffect(() => { localStorage.setItem("tt_tab", tab); }, [tab]);

  const load = useCallback(async () => {
    try { setData(await api("status")); setAuthed(true); } catch (e) { if (e.message === "401") setAuthed(false); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);
  useEffect(() => { if (sel) api(`history/${sel}?hours=${hours}`).then(setHist).catch(() => { }); }, [sel, hours, data]);

  if (authed === null) return null;
  if (!authed) return (
    <div className="login"><div className="logo">T<b>T</b> Monitor</div>
      <input type="password" placeholder="Password" value={pw} onChange={(e) => setPw(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && document.getElementById("go").click()} />
      <button id="go" onClick={async () => { try { await api("login", { password: pw }); setErr(""); load(); } catch (e) { setErr(e.message); } }}>Log in</button>
      {err && <div className="err">{err}</div>}</div>
  );
  if (!data) return <div className="wrap">Loading…</div>;

  const down = data.projects.filter((p) => p.latest && !p.latest.ok);
  const cur = data.projects.find((p) => p.key === sel);
  return (
    <>
      <div className="top"><div className="logo">T<b>T</b> Monitor</div>
        <div><button disabled={busy} onClick={async () => { setBusy(true); await api("check-now", {}).catch(() => { }); await load(); setBusy(false); }}>{busy ? "Checking…" : "Check now"}</button>{" "}
          <button className="ghost" onClick={async () => { await api("logout", {}); setAuthed(false); }}>Log out</button></div></div>
      <div className="wrap">
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          <button className={tab === "uptime" ? "" : "ghost"} onClick={() => setTab("uptime")}>Uptime</button>
          <button className={tab === "usage" ? "" : "ghost"} onClick={() => setTab("usage")}>Usage &amp; downloads</button>
          <button className={tab === "incidents" ? "" : "ghost"} onClick={() => setTab("incidents")}>Incidents</button>
        </div>
        {tab === "usage" ? <Usage /> : tab === "incidents" ? <Incidents /> : <>
          <div className={"banner " + (down.length ? "bad" : "ok")}>{down.length ? `${down.length} project${down.length > 1 ? "s" : ""} down: ${down.map((p) => p.name).join(", ")}` : "All systems operational"}</div>
          <div className="grid">
            {data.projects.map((p) => {
              const st = !p.latest ? "" : p.latest.ok ? "up" : "down";
              return (
                <div key={p.key} className={"card " + (sel === p.key ? "sel" : "")} onClick={() => setSel(p.key)}>
                  <div className="row"><b><span className={"dot " + st} />{p.name}</b><span className="mut">{!p.latest ? "no data" : p.latest.ok ? "Online" : "Down"}</span></div>
                  <div className="big">{p.uptime == null ? "—" : p.uptime + "%"}</div><div className="mut">uptime, last 24h</div>
                  <div className="row" style={{ marginTop: 10 }}><span className="mut">Avg {p.avg_ms ?? "—"} ms</span><span className="mut">{ago(p.latest?.ts)}</span></div>
                  {p.ssl && (p.ssl.days != null ? <div className="mut" style={{ marginTop: 6, color: p.ssl.days <= 14 ? "#ef4444" : undefined }}>🔒 SSL expires in {p.ssl.days} days</div> : p.ssl.error && <div className="mut" style={{ marginTop: 6 }}>🔒 SSL check failed</div>)}
                  {p.latest && !p.latest.ok && <div className="err" style={{ marginTop: 8, fontSize: 13 }}>{p.latest.error}</div>}
                </div>
              );
            })}
          </div>
          {cur && (
            <div className="panel">
              <div className="row"><b>{cur.name}</b>
                <select value={hours} onChange={(e) => setHours(+e.target.value)}><option value={24}>Last 24 hours</option><option value={72}>Last 3 days</option><option value={168}>Last 7 days</option><option value={720}>Last 30 days</option></select></div>
              <p className="mut">{cur.url} · last outage: {cur.last_down ? `${ago(cur.last_down.ts)} (${cur.last_down.error})` : "none recorded"}</p>
              <Chart pts={hist} />
            </div>
          )}
          <p className="mut" style={{ marginTop: 18 }}>Checks run every {data.interval}s. Updates every 30s.</p>
        </>}
      </div>
    </>
  );
}
