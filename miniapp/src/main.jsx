import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

try { window.Telegram?.WebApp?.ready(); } catch {}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
