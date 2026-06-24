import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AlphaBot/1.0)"}
_TROY_OZ_GRAMS = 31.1035


async def get_market_snapshot() -> dict:
    """
    Fetches live market data from MOEX ISS and CBR.
    Returns dict:
        imoex, imoex_change  – МосБиржа index and daily change
        usd_rub              – CBR official USD/RUB rate
        gold_rub_gram        – CBR gold price in RUB per gram (previous business day)
        gold_usd_oz          – gold price in USD per troy ounce (derived)
        updated_at           – timestamp string
    """
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
        imoex, imoex_open = await _fetch_imoex(session)
        usd_rub = await _fetch_usd_rub_cbr(session)
        gold_rub_gram = await _fetch_gold_cbr(session)

    imoex_change = None
    if imoex is not None and imoex_open:
        imoex_change = round(imoex - imoex_open, 2)

    gold_usd_oz = None
    if gold_rub_gram and usd_rub:
        gold_usd_oz = round((gold_rub_gram * _TROY_OZ_GRAMS) / usd_rub, 2)

    return {
        "imoex": imoex,
        "imoex_change": imoex_change,
        "usd_rub": usd_rub,
        "gold_rub_gram": gold_rub_gram,
        "gold_usd_oz": gold_usd_oz,
        "updated_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }


async def _fetch_imoex(session: aiohttp.ClientSession) -> tuple[float | None, float | None]:
    """Returns (current_value, open_value) for IMOEX index."""
    try:
        url = (
            "https://iss.moex.com/iss/engines/stock/markets/index/boards/SNDX"
            "/securities/IMOEX.json?iss.meta=off&iss.only=marketdata"
        )
        async with session.get(url) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.json(content_type=None)

        cols = data["marketdata"]["columns"]
        rows = data["marketdata"]["data"]
        if not rows:
            return None, None

        row = rows[0]
        current = _col(row, cols, "CURRENTVALUE") or _col(row, cols, "LASTVALUE")
        open_val = _col(row, cols, "OPEN")
        return current, open_val
    except Exception:
        return None, None


async def _fetch_usd_rub_cbr(session: aiohttp.ClientSession) -> float | None:
    """CBR official daily USD/RUB rate."""
    try:
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            text = await resp.text(encoding="windows-1251")
        root = ET.fromstring(text)
        for valute in root.findall("Valute"):
            if _xml_text(valute, "CharCode") == "USD":
                value = _xml_text(valute, "Value")
                nominal = _xml_text(valute, "Nominal") or "1"
                if value:
                    return round(float(value.replace(",", ".")) / int(nominal), 4)
        return None
    except Exception:
        return None


async def _fetch_gold_cbr(session: aiohttp.ClientSession) -> float | None:
    """
    CBR gold accounting price in RUB per gram.
    Source: cbr.ru/hd_base/metall/metall_base_new/ (XML_metall.asp endpoint).
    Requests last 7 days to cover weekends/holidays; takes the most recent record.
    Note: Code is an XML attribute on <Record>, not a child element.
    """
    today = date.today()
    d_from = (today - timedelta(days=7)).strftime("%d/%m/%Y")
    d_to = (today - timedelta(days=1)).strftime("%d/%m/%Y")
    try:
        url = f"https://www.cbr.ru/scripts/XML_metall.asp?date_req1={d_from}&date_req2={d_to}"
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            text = await resp.text(encoding="windows-1251")
        root = ET.fromstring(text)
        gold_records = [r for r in root.findall("Record") if r.get("Code") == "1"]
        if gold_records:
            price = _xml_text(gold_records[-1], "Buy")
            if price:
                return float(price.replace(",", "."))
    except Exception:
        pass
    return None


def _col(row: list, cols: list, name: str):
    try:
        return row[cols.index(name)]
    except (ValueError, IndexError):
        return None


def _xml_text(element, tag: str) -> str | None:
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else None


def format_snapshot(snap: dict) -> str:
    lines = [f"🌅 <b>Рыночный брифинг</b> — {snap['updated_at']}\n"]

    # IMOEX
    if snap["imoex"] is not None:
        val = f"{snap['imoex']:,.2f}".replace(",", " ")
        change_str = ""
        if snap["imoex_change"] is not None:
            sign = "+" if snap["imoex_change"] >= 0 else ""
            arrow = "📈" if snap["imoex_change"] >= 0 else "📉"
            change_str = f"  {arrow} {sign}{snap['imoex_change']:,.2f}"
        lines.append(f"📊 <b>Индекс МосБиржи:</b> {val} пт{change_str}")
    else:
        lines.append("📊 <b>Индекс МосБиржи:</b> нет данных")

    # USD/RUB
    if snap["usd_rub"] is not None:
        lines.append(f"💵 <b>Курс доллара (ЦБ):</b> {snap['usd_rub']:,.2f} ₽")
    else:
        lines.append("💵 <b>Курс доллара:</b> нет данных")

    # Gold in USD per troy ounce
    if snap["gold_usd_oz"] is not None:
        usd_fmt = f"{snap['gold_usd_oz']:,.2f}".replace(",", " ")
        lines.append(f"🥇 <b>Золото:</b> ${usd_fmt} / тр. унц.")
    else:
        lines.append("🥇 <b>Золото (USD):</b> нет данных")

    # Gold in RUB per gram
    if snap["gold_rub_gram"] is not None:
        rub_fmt = f"{snap['gold_rub_gram']:,.2f}".replace(",", " ")
        lines.append(f"🥇 <b>Золото (ЦБ):</b> {rub_fmt} ₽ / г")
    else:
        lines.append("🥇 <b>Золото (RUB):</b> нет данных")

    lines.append("\n<i>📌 Источники: ЦБ РФ · МосБиржа · Учётная цена предыдущего дня</i>")
    return "\n".join(lines)
