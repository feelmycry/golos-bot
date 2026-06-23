import aiohttp
from bs4 import BeautifulSoup

_SOURCES = [
    {
        "url": "https://alfabank.ru/alfa-investor/",
        "name": "АльфаБанк Инвестор",
        "article_selectors": ["article", ".news-item", ".card", ".article-item", ".news__item"],
        "title_selectors": ["h2", "h3", ".title", ".card__title", ".news__title", "a"],
        "text_selectors": ["p", ".description", ".card__text", ".summary", ".news__text"],
    },
    {
        "url": "https://bcs-express.ru/novosti-i-analitika",
        "name": "БКС Экспресс",
        "article_selectors": ["article", ".article-list__item", ".news-list__item", ".post", ".feed__item"],
        "title_selectors": ["h2", "h3", ".article-list__title", ".title", ".feed__title", "a"],
        "text_selectors": ["p", ".article-list__text", ".lead", ".description", ".feed__text"],
    },
]

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


async def fetch_news(max_per_source: int = 5) -> list[dict]:
    results = []
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
        for source in _SOURCES:
            try:
                items = await _fetch_source(session, source, max_per_source)
                results.extend(items)
            except Exception:
                continue
    return results[:10]


async def _fetch_source(session: aiohttp.ClientSession, source: dict, limit: int) -> list[dict]:
    async with session.get(source["url"]) as resp:
        if resp.status != 200:
            return []
        html = await resp.text(errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    articles = []

    for selector in source["article_selectors"]:
        found = soup.select(selector)
        if len(found) >= 2:
            for item in found[:limit]:
                title = _extract_text(item, source["title_selectors"])
                text = _extract_text(item, source["text_selectors"])
                if title and len(title) > 10:
                    articles.append({
                        "title": title[:200],
                        "text": text[:400] if text else "",
                        "source": source["name"],
                    })
            if articles:
                break

    # Fallback: grab meaningful links
    if not articles:
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if 20 < len(text) < 200:
                articles.append({"title": text, "text": "", "source": source["name"]})
                if len(articles) >= limit:
                    break

    return articles[:limit]


def _extract_text(element, selectors: list[str]) -> str:
    for selector in selectors:
        found = element.select_one(selector)
        if found:
            text = found.get_text(strip=True)
            if text:
                return text
    return ""


def format_news_for_prompt(news_items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(news_items, 1):
        lines.append(f"{i}. [{item['source']}] {item['title']}")
        if item["text"]:
            lines.append(f"   {item['text']}")
    return "\n".join(lines)
