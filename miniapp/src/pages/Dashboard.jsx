import { useApi } from "../api";
import XPBar from "../components/XPBar";
import DailyTask from "../components/DailyTask";

export default function Dashboard() {
  const { data: me, loading: meLoading, refetch: refetchMe } = useApi("/api/me");
  const { data: daily, loading: dailyLoading, refetch: refetchDaily } = useApi("/api/daily");

  if (meLoading || dailyLoading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  const streak = me?.streak_days || 0;

  return (
    <div className="page">
      {/* Header */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 17 }}>{me?.first_name || "Игрок"}</div>
            <div style={{ color: "var(--hint)", fontSize: 13 }}>{me?.status}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontWeight: 700, fontSize: 18 }}>💰 {me?.coins?.toLocaleString()} ИР</div>
            {streak > 0 && <div style={{ fontSize: 12, color: "#ff9500" }}>🔥 {streak} дн. +{Math.round((me.streak_mult - 1) * 100)}% XP</div>}
          </div>
        </div>
        <XPBar xpIn={me?.xp_in_level || 0} xpFor={me?.xp_for_level || 1} level={me?.level || 1} />
      </div>

      {/* Guild */}
      {me?.guild && (
        <div className="card" style={{ marginBottom: 12 }}>
          <span>{me.guild.emoji} <b>{me.guild.name}</b></span>
          <span style={{ float: "right", color: "var(--hint)", fontSize: 13 }}>Рейтинг #{me.rank}</span>
        </div>
      )}

      {/* Daily tasks */}
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>📋 Задания дня</div>
        {daily?.tasks?.map((t) => (
          <DailyTask key={t.id} task={t} onClaim={() => { refetchDaily(); refetchMe(); }} />
        ))}
      </div>
    </div>
  );
}
