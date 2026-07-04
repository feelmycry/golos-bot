import React from 'react';

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getInitData() {
  try { return window.Telegram?.WebApp?.initData || ""; } catch { return ""; }
}

function getUserIdFallback() {
  try { return String(window.Telegram?.WebApp?.initDataUnsafe?.user?.id || ""); } catch { return ""; }
}

const _token = (() => {
  try { return new URLSearchParams(window.location.search).get('t') || ""; } catch { return ""; }
})();

export async function apiFetch(path, opts = {}) {
  const url = _token ? `${BASE}${path}${path.includes('?') ? '&' : '?'}t=${_token}` : `${BASE}${path}`;
  const res = await fetch(url, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      "X-Telegram-User-Id": getUserIdFallback(),
      "ngrok-skip-browser-warning": "true",
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export function useApi(path, deps = []) {
  const [state, setState] = React.useState({ data: null, loading: true, error: null });

  const refetch = React.useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    apiFetch(path)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error) => setState({ data: null, loading: false, error }));
  }, [path]);

  React.useEffect(() => {
    // Small delay to allow Telegram Desktop to inject window.Telegram.WebApp
    const t = setTimeout(refetch, 300);
    return () => clearTimeout(t);
  }, [refetch, ...deps]);

  return { ...state, refetch };
}
