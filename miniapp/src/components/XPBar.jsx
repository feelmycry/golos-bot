export default function XPBar({ xpIn, xpFor, level }) {
  const pct = xpFor > 0 ? Math.min(100, Math.round((xpIn / xpFor) * 100)) : 0;
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--hint)", marginBottom: 4 }}>
        <span>Ур. {level}</span>
        <span>{xpIn} / {xpFor} XP</span>
      </div>
      <div style={{ background: "rgba(0,0,0,0.1)", borderRadius: 8, height: 8, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, background: "var(--btn)", height: "100%", borderRadius: 8, transition: "width 0.5s" }} />
      </div>
    </div>
  );
}
