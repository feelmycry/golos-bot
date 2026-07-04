import { useState } from "react";
import NavBar from "./components/NavBar";
import Dashboard from "./pages/Dashboard";
import Map from "./pages/Map";
import Exchange from "./pages/Exchange";
import Leaderboard from "./pages/Leaderboard";
import Profile from "./pages/Profile";

const PAGES = { dashboard: Dashboard, map: Map, exchange: Exchange, leaders: Leaderboard, profile: Profile };

function NoTelegram() {
  return (
    <div style={{ padding: 32, textAlign: "center", color: "var(--text)" }}>
      <div style={{ fontSize: 48, marginBottom: 16 }}>📱</div>
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 8 }}>Откройте через Telegram</div>
      <div style={{ color: "var(--hint)", fontSize: 14 }}>
        Это приложение работает только внутри Telegram.<br />
        Нажмите кнопку «🎮 Играть» в боте.
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const hasInitData = !!window.Telegram?.WebApp?.initData;
  if (!hasInitData) return <NoTelegram />;
  const Page = PAGES[tab];
  return (
    <>
      <Page />
      <NavBar active={tab} onSelect={setTab} />
    </>
  );
}
