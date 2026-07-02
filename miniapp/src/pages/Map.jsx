import { useState } from "react";
import { useApi, apiFetch } from "../api";
import QuestCard from "../components/QuestCard";

export default function Map() {
  const { data: locations, loading, refetch } = useApi("/api/map");
  const [selectedLoc, setSelectedLoc] = useState(null);
  const [locDetail, setLocDetail] = useState(null);
  const [selectedQuest, setSelectedQuest] = useState(null);
  const [collecting, setCollecting] = useState(false);

  async function openLocation(loc) {
    if (!loc.unlocked || !loc.id) return;
    setSelectedLoc(loc);
    setLocDetail(null);
    const detail = await apiFetch(`/api/map/${loc.id}`);
    setLocDetail(detail);
  }

  async function collect(locId) {
    setCollecting(true);
    try {
      await apiFetch(`/api/map/${locId}/collect`, { method: "POST" });
      refetch();
    } finally {
      setCollecting(false);
    }
  }

  if (loading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  // Quest view
  if (selectedQuest && selectedLoc) {
    return (
      <div className="page">
        <button onClick={() => setSelectedQuest(null)} style={{ background: "none", border: "none", color: "var(--btn)", fontSize: 16, cursor: "pointer", marginBottom: 10 }}>← {selectedLoc.name}</button>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>{selectedQuest.title}</div>
        <QuestCard quest={selectedQuest} locId={selectedLoc.id} onDone={() => { setSelectedQuest(null); openLocation(selectedLoc); }} />
      </div>
    );
  }

  // Location detail view
  if (selectedLoc && locDetail) {
    return (
      <div className="page">
        <button onClick={() => setSelectedLoc(null)} style={{ background: "none", border: "none", color: "var(--btn)", fontSize: 16, cursor: "pointer", marginBottom: 10 }}>← Карта</button>
        <div className="card" style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>{selectedLoc.emoji} {locDetail.name}</div>
          <div style={{ color: "var(--hint)", fontSize: 13, margin: "6px 0" }}>{locDetail.sector}</div>
          <div style={{ fontSize: 13 }}>{locDetail.description?.replace(/<[^>]+>/g, "")}</div>
          {selectedLoc.can_collect && (
            <button className="btn" style={{ marginTop: 10 }} disabled={collecting}
              onClick={() => collect(selectedLoc.id)}>
              Собрать {selectedLoc.collect_amount} ИР пассивного дохода
            </button>
          )}
        </div>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Квесты ({selectedLoc.quests_done}/{selectedLoc.quests_total})</div>
        {locDetail.quests?.map((q) => (
          <div key={q.id} className="card" onClick={() => !q.completed && setSelectedQuest(q)}
            style={{ cursor: q.completed ? "default" : "pointer", opacity: q.completed ? 0.6 : 1, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{q.title}</div>
              <div style={{ fontSize: 12, color: "var(--hint)" }}>+{q.xp} XP · +{q.coins} ИР</div>
            </div>
            {q.completed ? <span style={{ color: "#4cd964" }}>✅</span> : <span style={{ color: "var(--btn)" }}>▶</span>}
          </div>
        ))}
      </div>
    );
  }

  // Map overview
  return (
    <div className="page">
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 12 }}>🗺 Карта локаций</div>
      {locations?.map((loc, i) => (
        <div key={loc.id || i} className="card" onClick={() => openLocation(loc)}
          style={{ cursor: loc.unlocked && loc.id ? "pointer" : "default", opacity: loc.unlocked ? 1 : 0.5 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{loc.emoji} {loc.name}</div>
              <div style={{ fontSize: 12, color: "var(--hint)" }}>{loc.sector} {!loc.unlocked ? `· Ур. ${loc.min_level}` : ""}</div>
            </div>
            <div style={{ textAlign: "right", fontSize: 12 }}>
              {loc.unlocked && loc.id
                ? <><span className="badge">{loc.quests_done}/{loc.quests_total}</span>{loc.can_collect && <div style={{ color: "#ff9500", marginTop: 2 }}>💰 {loc.collect_amount}</div>}</>
                : <span>🔒</span>
              }
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
