import aiohttp
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}
_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def get_dividend_info(ticker: str) -> dict | None:
    """
    Parse dohod.ru/ik/analytics/dividend/{ticker} for dividend forecasts and DSI.
    Returns dict with: forecast (list), dsi, next_date, next_amount, next_yield, history (list)
    """
    url = f"https://www.dohod.ru/ik/analytics/dividend/{ticker.lower()}"
    try:
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(url) as r:
                if r.status == 404:
                    return None
                if r.status != 200:
                    return None
                html = await r.text()
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")

    result: dict = {
        "forecast": [],
        "history": [],
        "dsi": None,
        "next_date": None,
        "next_amount": None,
        "next_yield": None,
    }

    # DSI — ищем в тексте страницы
    dsi_el = soup.find(string=lambda t: t and "DSI" in t)
    if dsi_el:
        parent = dsi_el.find_parent()
        if parent:
            # Find the nearby number
            import re
            m = re.search(r"DSI[:\s=]*([0-9]+[.,][0-9]+)", str(parent))
            if not m:
                # Try sibling
                sib = parent.find_next_sibling()
                if sib:
                    m = re.search(r"([0-9]+[.,][0-9]+)", sib.get_text())
            if m:
                result["dsi"] = m.group(1).replace(",", ".")

    # Таблица дивидендов
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]

        # Ищем таблицу с нужными колонками
        has_div = any("дивид" in h for h in headers)
        has_date = any("дат" in h or "реестр" in h for h in headers)
        if not (has_div and has_date):
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            vals = [c.get_text(strip=True) for c in cells]

            entry = {
                "period": vals[0] if len(vals) > 0 else "",
                "amount": vals[1] if len(vals) > 1 else "",
                "date": vals[2] if len(vals) > 2 else "",
                "yield": vals[3] if len(vals) > 3 else "",
            }
            if not entry["amount"] or not entry["period"]:
                continue

            # Определяем прогноз vs история по наличию "прогноз" или будущей даты
            text_row = " ".join(vals).lower()
            if "прогноз" in text_row or "оценк" in text_row or "forecast" in text_row:
                result["forecast"].append(entry)
                if result["next_amount"] is None:
                    result["next_amount"] = entry["amount"]
                    result["next_date"] = entry["date"]
                    result["next_yield"] = entry["yield"]
            else:
                result["history"].append(entry)

        if result["forecast"] or result["history"]:
            break

    return result if (result["forecast"] or result["history"] or result["dsi"]) else None
