const TABS = [
  { id: "dashboard", emoji: "🏠", label: "Главная" },
  { id: "map",       emoji: "🗺",  label: "Карта" },
  { id: "exchange",  emoji: "📈",  label: "Биржа" },
  { id: "leaders",   emoji: "🏆",  label: "Рейтинг" },
  { id: "profile",   emoji: "👤",  label: "Профиль" },
];

export default function NavBar({ active, onSelect }) {
  return (
    <nav style={{
      position: "fixed", bottom: 0, left: 0, right: 0,
      display: "flex", background: "var(--secondary)",
      borderTop: "1px solid rgba(0,0,0,0.08)", paddingBottom: "env(safe-area-inset-bottom)"
    }}>
      {TABS.map((t) => (
        <button key={t.id} onClick={() => onSelect(t.id)}
          style={{
            flex: 1, padding: "8px 0", border: "none", background: "none", cursor: "pointer",
            color: active === t.id ? "var(--btn)" : "var(--hint)", fontSize: 11,
            display: "flex", flexDirection: "column", alignItems: "center", gap: 2
          }}>
          <span style={{ fontSize: 22 }}>{t.emoji}</span>
          {t.label}
        </button>
      ))}
    </nav>
  );
}
