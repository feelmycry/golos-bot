import aiohttp

_BASE = "https://iss.moex.com/iss"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; InvestBot/1.0)"}
_TIMEOUT = aiohttp.ClientTimeout(total=12)
_STOCK_GROUPS = {"stock_shares", "stock_dr"}


def _rows(block: dict) -> list[dict]:
    cols = block.get("columns", [])
    return [dict(zip(cols, row)) for row in block.get("data", [])]


async def search_securities(query: str) -> list[dict]:
    """Returns list of {secid, shortname, name, group} for stocks matching query."""
    try:
        params = {
            "q": query,
            "iss.meta": "off",
            "securities.columns": "secid,shortname,name,type,group,primary_boardid",
            "is_trading": "1",
        }
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(f"{_BASE}/securities.json", params=params) as r:
                if r.status != 200:
                    return []
                data = await r.json(content_type=None)
        results = _rows(data.get("securities", {}))
        return [x for x in results if x.get("group") in _STOCK_GROUPS][:8]
    except Exception:
        return []


async def get_security_price(ticker: str) -> dict | None:
    """Current price and market data for a ticker on TQBR."""
    try:
        url = f"{_BASE}/engines/stock/markets/shares/boards/TQBR/securities/{ticker}.json"
        params = {"iss.meta": "off", "iss.only": "securities,marketdata"}
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(url, params=params) as r:
                if r.status != 200:
                    return None
                data = await r.json(content_type=None)
        secs = _rows(data.get("securities", {}))
        mdata = _rows(data.get("marketdata", {}))
        if not secs or not mdata:
            return None
        sec, md = secs[0], mdata[0]
        price = md.get("LAST") or md.get("LCURRENTPRICE") or md.get("MARKETPRICE")
        return {
            "ticker": ticker,
            "shortname": sec.get("SHORTNAME") or ticker,
            "price": price,
            "change_pct": md.get("LASTCHANGEPRC"),
            "open": md.get("OPEN"),
            "high": md.get("HIGH"),
            "low": md.get("LOW"),
            "vol_rub": md.get("VALTODAY"),
            "market_cap": sec.get("ISSUECAPITALIZATION"),
        }
    except Exception:
        return None


async def get_dividends(ticker: str) -> list[dict]:
    """Dividend history from MOEX ISS, newest first."""
    try:
        params = {"iss.meta": "off"}
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(f"{_BASE}/securities/{ticker}/dividends.json", params=params) as r:
                if r.status != 200:
                    return []
                data = await r.json(content_type=None)
        rows = _rows(data.get("dividends", {}))
        rows.sort(key=lambda x: x.get("registryclosedate") or "", reverse=True)
        return rows[:12]
    except Exception:
        return []


async def get_orderbook(ticker: str, depth: int = 8) -> dict | None:
    """Current order book: {buys: [...], sells: [...]}."""
    try:
        url = f"{_BASE}/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/orderbook.json"
        params = {"iss.meta": "off", "depth": depth}
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(url, params=params) as r:
                if r.status != 200:
                    return None
                data = await r.json(content_type=None)
        rows = _rows(data.get("orderbook", {}))
        buys = sorted([x for x in rows if x.get("BUYSELL") == "B"],
                      key=lambda x: x.get("PRICE") or 0, reverse=True)
        sells = sorted([x for x in rows if x.get("BUYSELL") == "S"],
                       key=lambda x: x.get("PRICE") or 0)
        return {"buys": buys[:depth], "sells": sells[:depth]}
    except Exception:
        return None
