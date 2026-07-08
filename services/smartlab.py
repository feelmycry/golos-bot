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

# (lowercase substring in header → our key); order matters — more specific first
_COL_PATTERNS = [
    ("ev/ebitda", "ev_ebitda"),
    ("долг/ebitda", "debt_ebitda"),
    ("p/e",  "p_e"),
    ("p/s",  "p_s"),
    ("p/b",  "p_bv"),
    ("roe",  "roe"),
    ("roa",  "roa"),
    ("дд ао", "div_yield"),
    ("капит", "market_cap_bln"),
]

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
    Parse current multipliers from Smart-Lab fundamentals summary page.
    Handles both non-financial (Table 0, has EV/EBITDA) and financial/bank
    (Table 1, has RoE/RoA) sectors by searching all tables for the ticker row.
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

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers_lower = [c.get_text(strip=True).lower() for c in header_cells]

        # Must have a "тикер" column
        ticker_col = next((i for i, h in enumerate(headers_lower) if "тикер" in h), None)
        if ticker_col is None:
            continue

        # Build column index map (first match wins per key)
        col_idx: dict[str, int] = {}
        for i, h in enumerate(headers_lower):
            for pattern, key in _COL_PATTERNS:
                if pattern in h and key not in col_idx:
                    col_idx[key] = i
                    break

        if not col_idx:
            continue

        # Find the row for this ticker
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if ticker_col >= len(cells):
                continue
            if cells[ticker_col].get_text(strip=True).upper() != ticker_upper:
                continue

            result: dict = {}
            for key, idx in col_idx.items():
                if idx < len(cells):
                    val = _clean(cells[idx].get_text(strip=True))
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

    for table in soup.find_all("table"):
        txt = table.get_text().lower()
        if "выручка" not in txt and "ebitda" not in txt:
            continue

        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

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
