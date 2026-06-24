import re
import aiohttp
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}
_TIMEOUT = aiohttp.ClientTimeout(total=20)
_BASE = "https://www.e-disclosure.ru"

# Report type IDs on e-disclosure.ru
_REPORT_TYPES = {
    "msfo_annual": "56",   # Годовая консолидированная отчётность МСФО
    "msfo_semi":   "57",   # Полугодовая МСФО
    "rsbu_annual": "1",    # Годовая отчётность РСБУ
    "rsbu_quarter": "2",   # Квартальная РСБУ
}


async def find_company(name: str) -> str | None:
    """Search e-disclosure.ru by company name, return company page ID."""
    url = f"{_BASE}/poisk-po-soobshheniyam"
    params = {"query": name, "eventType": "55", "pageIndex": "1"}
    try:
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(url, params=params) as r:
                if r.status != 200:
                    return None
                html = await r.text()
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")
    # Company links look like: href="/portal/company.aspx?id=3537"
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/portal/company\.aspx\?id=(\d+)", href, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


async def get_reports(company_id: str, report_type_id: str) -> list[dict]:
    """
    Get list of financial reports for a company from e-disclosure.ru.
    Returns list of {title, date, url}
    """
    url = f"{_BASE}/portal/files.aspx"
    params = {"id": company_id, "type": report_type_id}
    try:
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as s:
            async with s.get(url, params=params) as r:
                if r.status != 200:
                    return []
                html = await r.text()
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    reports = []

    # Report links are PDF links in the page
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        # PDF links or document links
        if ".pdf" in href.lower() or "getfile" in href.lower() or "download" in href.lower():
            if not href.startswith("http"):
                href = _BASE + href
            title = a.get_text(strip=True) or "Документ"
            if not title or len(title) < 3:
                # Try parent element for title
                parent = a.find_parent(["td", "div", "li"])
                if parent:
                    title = parent.get_text(strip=True)[:80]

            # Try to find date near this link
            parent_row = a.find_parent("tr")
            date_str = ""
            if parent_row:
                cells = parent_row.find_all("td")
                for cell in cells:
                    txt = cell.get_text(strip=True)
                    if re.search(r"\d{2}\.\d{2}\.\d{4}", txt):
                        date_str = txt[:10]
                        break

            reports.append({"title": title[:100], "date": date_str, "url": href})
            if len(reports) >= 10:
                break

    return reports


async def get_all_reports(company_name: str) -> dict | None:
    """
    Find company on e-disclosure and return recent IFRS + RSBU reports.
    Returns {company_id, msfo: [...], rsbu: [...]}
    """
    company_id = await find_company(company_name)
    if not company_id:
        return None

    # Fetch IFRS annual and RSBU annual in parallel
    import asyncio
    msfo_task = asyncio.create_task(get_reports(company_id, _REPORT_TYPES["msfo_annual"]))
    rsbu_task = asyncio.create_task(get_reports(company_id, _REPORT_TYPES["rsbu_annual"]))
    msfo_semi_task = asyncio.create_task(get_reports(company_id, _REPORT_TYPES["msfo_semi"]))

    msfo, rsbu, msfo_semi = await asyncio.gather(msfo_task, rsbu_task, msfo_semi_task)

    return {
        "company_id": company_id,
        "msfo_annual": msfo[:5],
        "msfo_semi": msfo_semi[:3],
        "rsbu_annual": rsbu[:3],
        "company_url": f"{_BASE}/portal/company.aspx?id={company_id}",
    }


async def download_pdf(url: str, max_bytes: int = 15 * 1024 * 1024) -> bytes | None:
    """Download a PDF file, limited to max_bytes. Returns None if too large or error."""
    try:
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                content_length = r.content_length
                if content_length and content_length > max_bytes:
                    return None
                data = await r.read()
                if len(data) > max_bytes:
                    return None
                return data
    except Exception:
        return None
