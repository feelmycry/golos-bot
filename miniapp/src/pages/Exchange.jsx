import { useState } from "react";
import { useApi, apiFetch } from "../api";

export default function Exchange() {
  const { data: stocks, loading, refetch } = useApi("/api/stocks");
  const { data: me, refetch: refetchMe } = useApi("/api/me");
  const [selected, setSelected] = useState(null);
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function trade(action) {
    if (!selected || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await apiFetch(`/api/stocks/${selected.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ qty: Number(qty) }),
      });
      setMsg(res.success ? `${action === "buy" ? "Куплено" : "Продано"} ${qty} акций` : res.message);
      refetch();
      refetchMe();
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  if (selected) {
    const stock = stocks?.find((s) => s.id === selected.id) || selected;
    return (
      <div className="page">
        <button onClick={() => { setSelected(null); setMsg(""); }} style={{ background: "none", border: "none", color: "var(--btn)", fontSize: 16, cursor: "pointer", marginBottom: 10 }}>← Биржа</button>
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: 18 }}>{stock.name}</div>
          <div style={{ color: "var(--hint)", fontSize: 13 }}>{stock.ticker}</div>
          <div style={{ fontSize: 28, fontWeight: 700, margin: "10px 0" }}>{stock.price} ИР</div>
          <div style={{ color: stock.change_pct >= 0 ? "#4cd964" : "#ff3b30", fontSize: 15 }}>
            {stock.change_pct >= 0 ? "▲" : "▼"} {Math.abs(stock.change_pct).toFixed(2)}%
          </div>
          <div style={{ marginTop: 10, color: "var(--hint)", fontSize: 13 }}>Ваши акции: {stock.shares_owned}</div>
        </div>
        <div className="card">
          <div style={{ marginBottom: 10, fontWeight: 600 }}>Количество</div>
          <input type="number" min="1" value={qty} onChange={(e) => setQty(e.target.value)}
            style={{ width: "100%", padding: "10px", border: "1px solid rgba(0,0,0,0.15)", borderRadius: 8, fontSize: 16, background: "var(--bg)", color: "var(--text)", marginBottom: 10 }} />
          <div style={{ fontSize: 13, color: "var(--hint)", marginBottom: 10 }}>
            Сумма: {stock.price * Number(qty)} ИР · Баланс: {me?.coins?.toLocaleString()} ИР
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" disabled={busy} onClick={() => trade("buy")}>Купить</button>
            <button className="btn btn-outline" disabled={busy || stock.shares_owned === 0} onClick={() => trade("sell")}>Продать</button>
          </div>
          {msg && <div style={{ marginTop: 8, textAlign: "center", color: "var(--hint)", fontSize: 13 }}>{msg}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontWeight: 700, fontSize: 18 }}>📈 Биржа</div>
        <div style={{ color: "var(--hint)", fontSize: 13 }}>💰 {me?.coins?.toLocaleString()} ИР</div>
      </div>
      {stocks?.map((s) => (
        <div key={s.id} className="card" onClick={() => { setSelected(s); setQty(1); setMsg(""); }}
          style={{ cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 600 }}>{s.name}</div>
            <div style={{ fontSize: 12, color: "var(--hint)" }}>{s.ticker}{s.shares_owned > 0 ? ` · Ваши: ${s.shares_owned}` : ""}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontWeight: 700 }}>{s.price} ИР</div>
            <div style={{ fontSize: 12, color: s.change_pct >= 0 ? "#4cd964" : "#ff3b30" }}>
              {s.change_pct >= 0 ? "▲" : "▼"} {Math.abs(s.change_pct).toFixed(2)}%
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
