import React, { useEffect, useState } from "react";

const dur = (s) => (s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)} min` : s < 86400 ? `${(s / 3600).toFixed(1)} h` : `${(s / 86400).toFixed(1)} d`);
const th = { textAlign: "left", padding: "10px 8px", color: "#8b919c", fontWeight: 600, fontSize: 13 };
const td = { padding: "12px 8px", borderTop: "1px solid #262a33", fontSize: 14 };

export default function Incidents() {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    const go = () => fetch("/api/incidents", { credentials: "same-origin" }).then((r) => r.json()).then(setRows).catch(() => setRows([]));
    go(); const t = setInterval(go, 60000); return () => clearInterval(t);
  }, []);
  if (!rows) return <p className="mut">Loading…</p>;
  return (
    <div className="panel" style={{ marginTop: 0, overflowX: "auto" }}>
      <b>Incident log (last 30 days)</b>
      {!rows.length ? <p className="mut">No outages recorded. 🎉</p> : (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
          <thead><tr><th style={th}>Project</th><th style={th}>Started</th><th style={th}>Duration</th><th style={th}>Status</th><th style={th}>Reason</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}><td style={td}><b>{r.project}</b></td><td style={td}>{new Date(r.start * 1000).toLocaleString()}</td>
                <td style={td}>{dur(r.duration)}</td>
                <td style={{ ...td, color: r.ongoing ? "#ef4444" : "#22c55e", fontWeight: 600 }}>{r.ongoing ? "Ongoing" : "Resolved"}</td>
                <td style={{ ...td, color: "#8b919c" }}>{r.error || "—"}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
