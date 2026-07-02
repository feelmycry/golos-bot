import { useState } from "react";
import { apiFetch } from "../api";

export default function QuestCard({ quest, locId, onDone }) {
  const [selected, setSelected] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(idx) {
    if (result || busy) return;
    setSelected(idx);
    setBusy(true);
    try {
      const data = await apiFetch(`/api/map/${locId}/quests/${quest.id}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer_idx: idx }),
      });
      setResult(data);
    } finally {
      setBusy(false);
    }
  }

  const NUMS = ["①", "②", "③", "④"];

  return (
    <div className="card">
      <div style={{ fontSize: 13, color: "var(--hint)", marginBottom: 6 }}>{quest.story}</div>
      <div style={{ fontWeight: 600, marginBottom: 10 }}>{quest.question}</div>
      {quest.options.map((opt, i) => {
        let bg = "var(--secondary)";
        if (result) {
          if (result.correct && i === selected) bg = "#4cd96422";
          else if (!result.correct && i === selected) bg = "#ff3b3022";
        }
        return (
          <button key={i} onClick={() => submit(i)} disabled={!!result || busy}
            style={{ display: "block", width: "100%", textAlign: "left", padding: "10px 12px",
              marginBottom: 6, background: bg, border: "1.5px solid rgba(0,0,0,0.08)",
              borderRadius: 8, cursor: result ? "default" : "pointer", fontSize: 14 }}>
            {NUMS[i]} {opt}
          </button>
        );
      })}
      {result && (
        <div style={{ marginTop: 10 }}>
          <div style={{ color: result.correct ? "#4cd964" : "#ff3b30", fontWeight: 600, marginBottom: 4 }}>
            {result.correct ? `✅ +${result.xp_earned} XP, +${result.coins_earned} ИР` : "❌ Неверно"}
          </div>
          <div style={{ fontSize: 13, color: "var(--hint)" }}>{result.explanation}</div>
          {result.new_achievements?.map((a) => (
            <div key={a.id} style={{ marginTop: 6, color: "#ff9500" }}>🏅 Достижение: {a.emoji} {a.name}</div>
          ))}
          <button className="btn" style={{ marginTop: 10 }} onClick={onDone}>← К локации</button>
        </div>
      )}
    </div>
  );
}
