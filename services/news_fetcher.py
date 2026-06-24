import asyncio
import re
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

_PLAYWRIGHT_AVAILABLE = True
try:
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

_48H_LIMIT = 48


async def fetch_news() -> list[dict]:
    results = []

    if _PLAYWRIGHT_AVAILABLE:
        try:
            playwright_items = await _fetch_with_playwright()
            results.extend(playwright_items)
        except Exception:
            pass

    # Smart-Lab via aiohttp as fallback if playwright sources returned nothing
    if not results:
        try:
            smartlab_items = await _fetch_smartlab(10)
            results.extend(smartlab_items)
        except Exception:
            pass

    return results


async def _fetch_with_playwright() -> list[dict]:
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=_HEADERS["User-Agent"],
            locale="ru-RU",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        alfa_items = await _scrape_alfabank(page)
        results.extend(alfa_items)

        bcs_items = await _scrape_bcs(page)
        results.extend(bcs_items)

        await browser.close()

    return results


def _is_within_48h(date_str: str) -> bool:
    """Return True if date_str (ISO or YYYY-MM-DD) is within last 48 hours."""
    if not date_str:
        return True  # no date info → include by default
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_48H_LIMIT)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str[:19], fmt[:len(fmt)])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt >= cutoff
        except ValueError:
            continue
    return True  # unparseable date → include


def _extract_date_from_url(url: str) -> str:
    """Try to extract YYYY-MM-DD from URL path."""
    match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


async def _scrape_alfabank(page) -> list[dict]:
    try:
        await page.goto(
            "https://alfabank.ru/alfa-investor/",
            wait_until="domcontentloaded",
            timeout=25000,
        )
        await _wait_for_content(page, min_chars=1000, timeout_sec=10)

        # Extract all article links + attempt to get date from nearby <time> or parent text
        links = await page.evaluate("""
            () => {
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                const seen = new Set();
                const results = [];

                for (const a of anchors) {
                    const url = a.href;
                    const title = a.innerText.trim().replace(/\\n/g, ' ').substring(0, 150);
                    const isArticle = url.includes('/alfa-investor/t/') &&
                                     !url.includes('#') &&
                                     !url.includes('/category/') &&
                                     url.length > 50 &&
                                     title.length > 15 &&
                                     !seen.has(url);
                    if (!isArticle) continue;
                    seen.add(url);

                    // Try to find a <time datetime="..."> near the link
                    let dateStr = '';
                    const container = a.closest('article, li, .card, [class*="item"], [class*="news"]') || a.parentElement;
                    if (container) {
                        const timeEl = container.querySelector('time[datetime]');
                        if (timeEl) dateStr = timeEl.getAttribute('datetime') || '';
                        if (!dateStr) {
                            // Fallback: look for date text pattern DD.MM.YYYY or YYYY-MM-DD
                            const txt = container.innerText || '';
                            const m = txt.match(/(\\d{4}-\\d{2}-\\d{2})/);
                            if (m) dateStr = m[1];
                        }
                    }

                    results.push({ href: url, text: title, dateStr: dateStr });
                }
                return results;
            }
        """)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=_48H_LIMIT)
        has_any_date = any(lnk.get("dateStr") for lnk in links)

        items = []
        for link in links:
            title = link.get("text", "").strip()
            if not title or len(title) <= 15:
                continue

            date_str = link.get("dateStr", "") or _extract_date_from_url(link.get("href", ""))

            if has_any_date and date_str:
                # We have reliable date info — filter strictly
                if not _is_within_48h(date_str):
                    continue
            # If no date info at all on the page, include everything (can't filter)

            items.append({
                "title": title[:200],
                "text": "",
                "source": "АльфаБанк Инвестор",
                "date": date_str,
            })

        return items
    except Exception:
        return []


async def _scrape_bcs(page) -> list[dict]:
    try:
        await page.goto(
            "https://bcs-express.ru/novosti-i-analitika",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        await _wait_for_content(page, min_chars=500, timeout_sec=8)

        links = await page.evaluate("""
            () => {
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                const seen = new Set();
                const results = [];

                for (const a of anchors) {
                    const url = a.href;
                    const title = a.innerText.trim().replace(/\\n/g, ' ').substring(0, 150);
                    const isArticle = url.includes('bcs-express.ru') &&
                                     !url.endsWith('/novosti-i-analitika') &&
                                     !url.includes('category') &&
                                     title.length > 15 &&
                                     !seen.has(url);
                    if (!isArticle) continue;
                    seen.add(url);

                    let dateStr = '';
                    const container = a.closest('article, li, .card, [class*="item"], [class*="news"]') || a.parentElement;
                    if (container) {
                        const timeEl = container.querySelector('time[datetime]');
                        if (timeEl) dateStr = timeEl.getAttribute('datetime') || '';
                        if (!dateStr) {
                            const txt = container.innerText || '';
                            const m = txt.match(/(\\d{4}-\\d{2}-\\d{2})/);
                            if (m) dateStr = m[1];
                        }
                    }

                    results.push({ href: url, text: title, dateStr: dateStr });
                }
                return results;
            }
        """)

        has_any_date = any(lnk.get("dateStr") for lnk in links)

        items = []
        for link in links:
            title = link.get("text", "").strip()
            if not title or len(title) <= 15:
                continue

            date_str = link.get("dateStr", "") or _extract_date_from_url(link.get("href", ""))

            if has_any_date and date_str:
                if not _is_within_48h(date_str):
                    continue

            items.append({
                "title": title[:200],
                "text": "",
                "source": "БКС Экспресс",
                "date": date_str,
            })

        return items
    except Exception:
        return []


async def _wait_for_content(page, min_chars: int = 500, timeout_sec: int = 10):
    for _ in range(timeout_sec):
        try:
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            if len(text) > min_chars:
                return
        except Exception:
            pass
        await asyncio.sleep(1)


async def _fetch_smartlab(limit: int) -> list[dict]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
        async with session.get("https://smart-lab.ru/news/") as resp:
            if resp.status != 200:
                return []
            html = await resp.text(errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    items = []
    for h3 in soup.find_all("h3"):
        a = h3.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        if len(title) > 15:
            items.append({"title": title[:200], "text": "", "source": "Smart-Lab", "date": ""})
            if len(items) >= limit:
                break
    return items


def format_news_for_prompt(news_items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(news_items, 1):
        date_tag = f" [{item['date']}]" if item.get("date") else ""
        lines.append(f"{i}. [{item['source']}]{date_tag} {item['title']}")
        if item.get("text"):
            lines.append(f"   {item['text']}")
    return "\n".join(lines)
