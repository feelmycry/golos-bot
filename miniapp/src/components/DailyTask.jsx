import { apiFetch } from "../api";
import { useState } from "react";

export default function DailyTask({ task, onClaim }) {
  const [busy, setBusy] = useState(false);
  const pct = Math.min(100, Math.round((task.progress / task.target) * 100));

  async function handleClaim() {
    setBusy(true);
    try {
      await apiFetch(`/api/daily/${task.id}/claim`, { method: "POST" });
      onClaim();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 14 }}>
        <span>{task.desc}</span>
        <span style={{ color: "var(--hint)" }}>{task.progress}/{task.target}</span>
      </div>
      <div style={{ background: "rgba(0,0,0,0.1)", borderRadius: 6, height: 6, marginBottom: 6 }}>
        <div style={{ width: `${pct}%`, background: task.completed ? "#4cd964" : "var(--btn)", height: "100%", borderRadius: 6 }} />
      </div>
      {task.completed && !task.claimed && (
        <button className="btn" disabled={busy} onClick={handleClaim}>
          Получить +{task.coins} ИР, +{task.xp} XP
        </button>
      )}
      {task.claimed && <div style={{ color: "#4cd964", fontSize: 13 }}>✅ Получено</div>}
    </div>
  );
}
