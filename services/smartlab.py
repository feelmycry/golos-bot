import re
import aiohttp
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Referer": "https://smart-lab.ru/",
}
_TIMEOUT = aiohttp.ClientTimeout(total=20)

_MULT_COLS = {
    "P/E": "p_e",
    "P/S": "p_s",
    "EV/EBITDA": "ev_ebitda",
    "P/BV": "p_bv",
    "ROE": "roe",
    "Долг/EBITDA": "debt_ebitda",
    "Дивиденды": "div_yield",
}

_FIN_ROWS_MAP = {
    "выручка": "revenue",
    "ebitda": "ebitda",
    "чистая прибыль": "net_profit",
    "свободный ден": "fcf",
    "чистый долг": "net_debt",
    "капитализация": "market_cap",
}


def _clean(s: str) -> str | None:
    if not s:
        return None
    s = s.strip().replace("\xa0", "").replace(" ", "")
    m = re.search(r"[-−]?[\d]+[.,]?[\d]*", s)
    return m.group().replace(",", ".").replace("−", "-") if m else None


async def get_multipliers(ticker: str) -> dict | None:
    """
    Parse current multipliers from Smart-Lab fundamentals summary table.
    This table is server-rendered and Google-indexed, so it's parseable.
    """
    url = "https://smart-lab.ru/q/shares_fundamental/"
    try:
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                html = await r.text()
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")
    ticker_upper = ticker.upper()

    # Find the main table with fundamentals
    table = None
    for t in soup.find_all("table"):
        txt = t.get_text()
        if "P/E" in txt and "EV/EBITDA" in txt:
            table = t
            break
    if not table:
        return None

    rows = table.find_all("tr")
    if len(rows) < 2:
        return None

    # Extract column headers
    header_row = rows[0]
    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]

    # Find column indices
    col_indices: dict[str, int] = {}
    for i, h in enumerate(headers):
        for col_label, key in _MULT_COLS.items():
            if col_label in h:
                col_indices[key] = i

    # Find the row for this ticker
    ticker_col = next((i for i, h in enumerate(headers) if "тикер" in h.lower() or "код" in h.lower()), 0)

    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        row_ticker = cells[ticker_col].get_text(strip=True).upper() if ticker_col < len(cells) else ""
        if row_ticker != ticker_upper:
            continue

        result: dict = {}
        for key, col_idx in col_indices.items():
            if col_idx < len(cells):
                val = _clean(cells[col_idx].get_text(strip=True))
                if val:
                    result[key] = val
        return result if result else None

    return None


async def get_financials(ticker: str) -> dict | None:
    """
    Parse annual financial statements from smart-lab.ru/q/{ticker}/f/y/
    Falls back gracefully if JS-rendered or blocked.
    """
    url = f"https://smart-lab.ru/q/{ticker.upper()}/f/y/"
    try:
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                html = await r.text()
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")
    result: dict = {"years": [], "metrics": {}}

    # Look for any table containing financial metrics
    for table in soup.find_all("table"):
        txt = table.get_text().lower()
        if "выручка" not in txt and "ebitda" not in txt:
            continue

        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

        # Extract years from header
        header_cells = rows[0].find_all(["th", "td"])
        years = []
        for cell in header_cells[1:]:
            t = cell.get_text(strip=True)
            if re.match(r"20\d{2}", t):
                years.append(t)
        if not years:
            continue

        result["years"] = years[-5:]

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower()

            key = None
            for pattern, metric_key in _FIN_ROWS_MAP.items():
                if pattern in label:
                    key = metric_key
                    break
            if not key:
                continue

            vals = []
            for cell in cells[1: len(years) + 1]:
                vals.append(_clean(cell.get_text(strip=True)))
            result["metrics"][key] = vals

        if result["metrics"]:
            return result

    return None
