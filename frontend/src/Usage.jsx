import React, { useEffect, useState } from "react";

const WINS = [["20m", "Last 20 min"], ["1h", "Last hour"], ["7d", "Last 7 days"], ["30d", "Last 30 days"]];
const METRICS = [["visitors", "Visitors"], ["views", "Page views"], ["clicks", "Link clicks"], ["downloads", "Downloads"], ["installs", "App installs"]];
const RANGES = [["24h", "24 hours"], ["7d", "7 days"], ["30d", "30 days"]];
const th = { textAlign: "right", padding: "10px 8px", color: "#8b919c", fontWeight: 600, fontSize: 13 };
const td = { textAlign: "right", padding: "12px 8px", borderTop: "1px solid #262a33", fontSize: 18, fontWeight: 600 };
const get = (p) => fetch("/api/" + p, { credentials: "same-origin" }).then((r) => r.json());

function Bars({ vals }) {
  const W = 300, H = 60, max = Math.max(1, ...vals), bw = W / vals.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 60 }}>
      {vals.map((v, i) => <rect key={i} x={i * bw + 0.5} y={H - (v / max) * (H - 2)} width={Math.max(1, bw - 1)} height={(v / max) * (H - 2)} fill="#f97316" opacity={v ? 1 : 0.15} />)}
    </svg>
  );
}

export default function Usage() {
  const [d, setD] = useState(null);
  const [live, setLive] = useState({ total: 0, by: {} });
  const [tl, setTl] = useState(null);
  const [m, setM] = useState("visitors");
  const [range, setRange] = useState("24h");
  const [err, setErr] = useState("");

  useEffect(() => {
    const go = () => { get("usage").then(setD).catch(() => setErr("Could not load usage.")); get("live").then(setLive).catch(() => { }); };
    go(); const t = setInterval(go, 30000); return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const go = () => get("timeline?range=" + range).then(setTl).catch(() => { });
    go(); const t = setInterval(go, 60000); return () => clearInterval(t);
  }, [range]);

  if (err) return <p className="err">{err}</p>;
  if (!d) return <p className="mut">Loading…</p>;
  const total = (w) => d.projects.reduce((n, p) => n + p.windows[w][m], 0);

  return (
    <>
      <div className="banner ok" style={{ background: "#14301f" }}>● {live.total} {live.total === 1 ? "visitor" : "visitors"} active now (last 5 min)</div>
      <div className="row" style={{ marginBottom: 14, flexWrap: "wrap", gap: 8, justifyContent: "flex-start" }}>
        {METRICS.map(([k, l]) => <button key={k} className={m === k ? "" : "ghost"} onClick={() => setM(k)}>{l}</button>)}
      </div>
      <div className="panel" style={{ marginTop: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={{ ...th, textAlign: "left" }}>Platform</th><th style={th}>Live now</th>{WINS.map(([k, l]) => <th key={k} style={th}>{l}</th>)}</tr></thead>
          <tbody>
            {d.projects.map((p) => (
              <tr key={p.key}><td style={{ ...td, textAlign: "left", fontSize: 15 }}>{p.name}</td>
                <td style={{ ...td, color: "#22c55e" }}>{live.by[p.key] || 0}</td>
                {WINS.map(([k]) => <td key={k} style={td}>{p.windows[k][m].toLocaleString()}</td>)}</tr>
            ))}
            <tr><td style={{ ...td, textAlign: "left", fontSize: 15, color: "#f97316" }}>All platforms</td>
              <td style={{ ...td, color: "#22c55e" }}>{live.total}</td>
              {WINS.map(([k]) => <td key={k} style={{ ...td, color: "#f97316" }}>{total(k).toLocaleString()}</td>)}</tr>
          </tbody>
        </table>
        <p className="mut">Visitors are counted once per browser or device in each time window. Refreshes every 30 seconds.</p>
      </div>

      <div className="row" style={{ marginTop: 22 }}><b>Trend: {METRICS.find((x) => x[0] === m)[1]}</b>
        <select value={range} onChange={(e) => setRange(e.target.value)}>{RANGES.map(([k, l]) => <option key={k} value={k}>Last {l}</option>)}</select></div>
      <div className="grid" style={{ marginTop: 10 }}>
        {tl && tl.projects.map((p) => {
          const vals = p.series[m], sum = m === "visitors" ? p.visitors_now : vals.reduce((a, b) => a + b, 0);
          const pct = m === "visitors" && p.visitors_prev > 0 ? Math.round(((p.visitors_now - p.visitors_prev) / p.visitors_prev) * 100) : null;
          return (
            <div key={p.key} className="card" style={{ cursor: "default" }}>
              <div className="row"><b>{p.name}</b>{pct !== null && <span style={{ color: pct >= 0 ? "#22c55e" : "#ef4444", fontWeight: 600 }}>{pct >= 0 ? "▲" : "▼"} {Math.abs(pct)}%</span>}</div>
              <div className="big">{sum.toLocaleString()}</div>
              <Bars vals={vals} />
              <div className="mut">{m === "visitors" ? "vs the previous period" : `per ${tl.step === 3600 ? "hour" : "day"}`}</div>
            </div>
          );
        })}
      </div>

      <div className="grid" style={{ marginTop: 18 }}>
        {d.projects.map((p) => (
          <div key={p.key} className="card" style={{ cursor: "default" }}>
            <b>{p.name}</b><p className="mut" style={{ margin: "8px 0 4px" }}>Top clicks (7 days)</p>
            {p.top.click.length ? p.top.click.map((c) => <div key={c.label} className="row"><span>{c.label}</span><b>{c.n}</b></div>) : <span className="mut">None yet</span>}
            <p className="mut" style={{ margin: "12px 0 4px" }}>Top downloads (7 days)</p>
            {p.top.download.length ? p.top.download.map((c) => <div key={c.label} className="row"><span>{c.label}</span><b>{c.n}</b></div>) : <span className="mut">None yet</span>}
          </div>
        ))}
      </div>
    </>
  );
}
