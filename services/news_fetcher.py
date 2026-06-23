import aiohttp
from bs4 import BeautifulSoup

# Primary: smart-lab.ru (reliable, no auth required)
# Secondary: user-specified sources (may require local network/cookies)
_SOURCES = [
    {
        "url": "https://smart-lab.ru/news/",
        "name": "Smart-Lab",
        "mode": "h3_links",  # uses <h3><a>title</a></h3> pattern
        "ssl": True,
    },
    {
        "url": "https://alfabank.ru/alfa-investor/",
        "name": "АльфаБанк Инвестор",
        "mode": "generic",
        "article_selectors": ["article", ".news-item", ".card", ".article-item", ".news__item"],
        "title_selectors": ["h2", "h3", ".title", ".card__title", "a"],
        "text_selectors": ["p", ".description", ".card__text", ".summary"],
        "ssl": True,
    },
    {
        "url": "https://bcs-express.ru/novosti-i-analitika",
        "name": "БКС Экспресс",
        "mode": "generic",
        "article_selectors": ["article", ".article-list__item", ".news-list__item", ".post", ".feed__item"],
        "title_selectors": ["h2", "h3", ".article-list__title", ".title", "a"],
        "text_selectors": ["p", ".article-list__text", ".lead", ".description"],
        "ssl": False,  # bypass SSL for this source
    },
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def fetch_news(max_per_source: int = 5) -> list[dict]:
    results = []
    timeout = aiohttp.ClientTimeout(total=15)
    for source in _SOURCES:
        if len(results) >= 10:
            break
        try:
            connector = aiohttp.TCPConnector(ssl=source.get("ssl", True))
            async with aiohttp.ClientSession(
                headers=_HEADERS, timeout=timeout, connector=connector
            ) as session:
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

    if source.get("mode") == "h3_links":
        return _parse_h3_links(soup, source["name"], limit)
    return _parse_generic(soup, source, limit)


def _parse_h3_links(soup: BeautifulSoup, source_name: str, limit: int) -> list[dict]:
    articles = []
    for h3 in soup.find_all("h3"):
        a = h3.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        if len(title) > 15:
            articles.append({"title": title[:200], "text": "", "source": source_name})
            if len(articles) >= limit:
                break
    return articles


def _parse_generic(soup: BeautifulSoup, source: dict, limit: int) -> list[dict]:
    articles = []
    for selector in source.get("article_selectors", []):
        found = soup.select(selector)
        if len(found) >= 2:
            for item in found[:limit]:
                title = _extract_text(item, source.get("title_selectors", []))
                text = _extract_text(item, source.get("text_selectors", []))
                if title and len(title) > 10:
                    articles.append({
                        "title": title[:200],
                        "text": text[:400] if text else "",
                        "source": source["name"],
                    })
            if articles:
                break

    # Fallback: meaningful links
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
