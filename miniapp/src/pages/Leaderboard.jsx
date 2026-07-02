import { useState } from "react";
import { useApi } from "../api";

const MEDALS = ["🥇", "🥈", "🥉"];

export default function Leaderboard() {
  const { data, loading } = useApi("/api/leaderboard");
  const [tab, setTab] = useState("alltime");

  if (loading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  const TABS = [
    { id: "alltime", label: "Всё время" },
    { id: "weekly",  label: "Неделя" },
    { id: "guilds",  label: "Гильдии" },
  ];

  const list = data?.[tab] || [];
  const myRank = tab === "weekly" ? data?.my_weekly_rank : data?.my_rank;

  return (
    <div className="page">
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 12 }}>🏆 Рейтинг</div>
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ flex: 1, padding: "8px 0", borderRadius: 8, border: "none", cursor: "pointer",
              background: tab === t.id ? "var(--btn)" : "var(--secondary)", color: tab === t.id ? "var(--btn-text)" : "var(--text)", fontWeight: 600, fontSize: 13 }}>
            {t.label}
          </button>
        ))}
      </div>
      {myRank && myRank > 3 && (
        <div className="card" style={{ marginBottom: 8, borderLeft: "3px solid var(--btn)" }}>
          Ваша позиция: #{myRank}
        </div>
      )}
      {list.map((entry, i) => (
        <div key={i} className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: i < 3 ? 22 : 16, minWidth: 28 }}>{i < 3 ? MEDALS[i] : `${i + 1}.`}</span>
            <div>
              <div style={{ fontWeight: 600 }}>{tab === "guilds" ? (entry.emoji + " " + entry.name) : (entry.first_name || `ID ${entry.user_id}`)}</div>
              {tab !== "guilds" && <div style={{ fontSize: 12, color: "var(--hint)" }}>{entry.username ? `@${entry.username}` : ""}</div>}
            </div>
          </div>
          <div style={{ fontWeight: 700 }}>
            {tab === "guilds" ? entry.total_xp : tab === "weekly" ? entry.xp_gained : entry.xp} XP
          </div>
        </div>
      ))}
      {list.length === 0 && <div style={{ textAlign: "center", color: "var(--hint)", paddingTop: 30 }}>Пока никого нет</div>}
    </div>
  );
}
