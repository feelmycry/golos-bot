import asyncio
import aiohttp
from bs4 import BeautifulSoup

# Try playwright first for JS-heavy sites, fallback to aiohttp for smart-lab
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


async def fetch_news(max_per_source: int = 5) -> list[dict]:
    results = []

    if _PLAYWRIGHT_AVAILABLE:
        try:
            playwright_items = await _fetch_with_playwright(max_per_source)
            results.extend(playwright_items)
        except Exception:
            pass

    # Smart-Lab via aiohttp as fallback / supplement
    if len(results) < max_per_source:
        try:
            smartlab_items = await _fetch_smartlab(max_per_source)
            results.extend(smartlab_items)
        except Exception:
            pass

    return results[:10]


async def _fetch_with_playwright(limit: int) -> list[dict]:
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

        # Source 1: alfabank.ru/alfa-investor/
        alfa_items = await _scrape_alfabank(page, limit)
        results.extend(alfa_items)

        # Source 2: bcs-express.ru
        bcs_items = await _scrape_bcs(page, limit)
        results.extend(bcs_items)

        await browser.close()

    return results


async def _scrape_alfabank(page, limit: int) -> list[dict]:
    try:
        await page.goto(
            "https://alfabank.ru/alfa-investor/",
            wait_until="domcontentloaded",
            timeout=25000,
        )
        await _wait_for_content(page, min_chars=1000, timeout_sec=10)

        links = await page.evaluate("""
            () => {
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                const seen = new Set();
                return anchors
                    .map(a => ({
                        href: a.href,
                        text: a.innerText.trim().replace(/\\n/g, ' ').substring(0, 150)
                    }))
                    .filter(a => {
                        const url = a.href;
                        const isArticle = url.includes('/alfa-investor/t/') &&
                                         !url.includes('#') &&
                                         !url.includes('/category/') &&
                                         url.length > 50 &&
                                         a.text.length > 15 &&
                                         !seen.has(url);
                        if (isArticle) seen.add(url);
                        return isArticle;
                    });
            }
        """)

        items = []
        for link in links[:limit]:
            title = link.get("text", "").strip()
            if title and len(title) > 15:
                items.append({
                    "title": title[:200],
                    "text": "",
                    "source": "АльфаБанк Инвестор",
                })
        return items
    except Exception:
        return []


async def _scrape_bcs(page, limit: int) -> list[dict]:
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
                return anchors
                    .map(a => ({
                        href: a.href,
                        text: a.innerText.trim().replace(/\\n/g, ' ').substring(0, 150)
                    }))
                    .filter(a => {
                        const url = a.href;
                        const isArticle = url.includes('bcs-express.ru') &&
                                         !url.endsWith('/novosti-i-analitika') &&
                                         !url.includes('category') &&
                                         a.text.length > 15 &&
                                         !seen.has(url);
                        if (isArticle) seen.add(url);
                        return isArticle;
                    });
            }
        """)

        items = []
        for link in links[:limit]:
            title = link.get("text", "").strip()
            if title and len(title) > 15:
                items.append({
                    "title": title[:200],
                    "text": "",
                    "source": "БКС Экспресс",
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
            items.append({"title": title[:200], "text": "", "source": "Smart-Lab"})
            if len(items) >= limit:
                break
    return items


def format_news_for_prompt(news_items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(news_items, 1):
        lines.append(f"{i}. [{item['source']}] {item['title']}")
        if item.get("text"):
            lines.append(f"   {item['text']}")
    return "\n".join(lines)
