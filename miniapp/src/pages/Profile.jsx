import { useApi } from "../api";

export default function Profile() {
  const { data: me, loading: meLoading } = useApi("/api/me");
  const { data: achievements, loading: achLoading } = useApi("/api/me/achievements");

  if (meLoading || achLoading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  const earned = achievements?.filter((a) => a.earned) || [];
  const locked = achievements?.filter((a) => !a.earned) || [];

  return (
    <div className="page">
      <div className="card" style={{ textAlign: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 40, marginBottom: 6 }}>👤</div>
        <div style={{ fontWeight: 700, fontSize: 20 }}>{me?.first_name}</div>
        <div style={{ color: "var(--hint)", marginBottom: 8 }}>{me?.status}</div>
        <div style={{ display: "flex", justifyContent: "space-around", fontSize: 14 }}>
          <div><b>{me?.xp?.toLocaleString()}</b><div style={{ color: "var(--hint)" }}>XP</div></div>
          <div><b>{me?.coins?.toLocaleString()}</b><div style={{ color: "var(--hint)" }}>ИР</div></div>
          <div><b>{me?.streak_days}</b><div style={{ color: "var(--hint)" }}>дн. серия</div></div>
          <div><b>#{me?.rank}</b><div style={{ color: "var(--hint)" }}>место</div></div>
        </div>
      </div>
      {me?.guild && (
        <div className="card" style={{ marginBottom: 12 }}>
          <span>{me.guild.emoji} <b>{me.guild.name}</b></span>
        </div>
      )}
      <div style={{ fontWeight: 600, marginBottom: 8 }}>🏅 Достижения ({earned.length}/{achievements?.length})</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
        {earned.map((a) => (
          <div key={a.id} className="card" style={{ textAlign: "center", padding: "10px 8px" }}>
            <div style={{ fontSize: 28 }}>{a.emoji}</div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{a.name}</div>
            <div style={{ fontSize: 11, color: "var(--hint)" }}>{a.desc}</div>
          </div>
        ))}
        {locked.map((a) => (
          <div key={a.id} className="card" style={{ textAlign: "center", padding: "10px 8px", opacity: 0.4 }}>
            <div style={{ fontSize: 28 }}>🔒</div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{a.name}</div>
            <div style={{ fontSize: 11, color: "var(--hint)" }}>{a.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
