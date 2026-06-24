import random
import aiohttp
from config import PEXELS_API_KEY

_CACHE: dict[str, list[str]] = {}

_QUERIES = {
    "young":     {"male": "young man portrait",          "female": "young woman portrait"},
    "middle":    {"male": "businessman portrait",         "female": "businesswoman portrait"},
    "adult":     {"male": "mature man portrait",          "female": "mature woman portrait"},
    "pensioner": {"male": "senior man portrait",          "female": "senior woman portrait"},
}


async def fetch_photos(cohort: str, gender: str, count: int = 8) -> list[str]:
    """Fetch and cache photo URLs from Pexels for the given cohort/gender."""
    if not PEXELS_API_KEY:
        return []

    cache_key = f"{cohort}_{gender}"
    if _CACHE.get(cache_key):
        return _CACHE[cache_key]

    query = _QUERIES.get(cohort, {}).get(gender, "person portrait")
    url = (
        f"https://api.pexels.com/v1/search"
        f"?query={query}&per_page={count}&orientation=portrait"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"Authorization": PEXELS_API_KEY}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                urls = [p["src"]["medium"] for p in data.get("photos", [])]
                if urls:
                    _CACHE[cache_key] = urls
                return urls
    except Exception:
        return []
