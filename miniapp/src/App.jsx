import { useState } from "react";
import NavBar from "./components/NavBar";
import Dashboard from "./pages/Dashboard";
import Map from "./pages/Map";
import Exchange from "./pages/Exchange";
import Leaderboard from "./pages/Leaderboard";
import Profile from "./pages/Profile";

const PAGES = { dashboard: Dashboard, map: Map, exchange: Exchange, leaders: Leaderboard, profile: Profile };

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const Page = PAGES[tab];
  return (
    <>
      <Page />
      <NavBar active={tab} onSelect={setTab} />
    </>
  );
}
