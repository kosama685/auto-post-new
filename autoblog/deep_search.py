from __future__ import annotations

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import SourceArticle
from .utils import clean_text, parse_datetime

USER_AGENT = "ArabicHerbalDeepSearchBot/1.0 (+reviewed content; contact: site owner)"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
def _get(url: str, params: dict | None = None) -> requests.Response:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.9"},
        timeout=20,
    )
    response.raise_for_status()
    return response


def search_searxng(
    query: str,
    instance_url: str = "https://searx.be",
    language: str = "en",
    limit: int = 10,
) -> list[SourceArticle]:
    if not query:
        return []

    endpoint = instance_url.rstrip("/") + "/search"
    params = {
        "format": "json",
        "q": query,
        "language": language,
        "categories": "news",
        "count": min(max(limit, 1), 20),
    }

    response = _get(endpoint, params=params)
    payload = response.json()
    articles: list[SourceArticle] = []

    for hit in (payload.get("results") or [])[:limit]:
        title = clean_text(hit.get("title", ""))
        url = hit.get("url", "")
        summary = clean_text(hit.get("content", ""))
        if not title or not url:
            continue
        articles.append(
            SourceArticle(
                title=title,
                summary=summary,
                content=summary,
                source_url=url,
                source_name="SearxNG",
                author=clean_text(hit.get("username", "Unknown")) or "Unknown",
                published_at=parse_datetime(hit.get("publishedAt", None)) or None,
                image_url="",
                raw=hit,
            )
        )
    return articles


def search_google_cse(
    query: str,
    api_key: str,
    cx: str,
    language: str = "en",
    limit: int = 10,
) -> list[SourceArticle]:
    if not api_key or not cx or not query:
        return []

    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": min(max(limit, 1), 10),
        "lr": f"lang_{language}" if language else "",
    }
    response = _get("https://www.googleapis.com/customsearch/v1", params=params)
    payload = response.json()
    items = payload.get("items", [])
    articles: list[SourceArticle] = []

    for item in items[:limit]:
        title = clean_text(item.get("title", ""))
        link = item.get("link", "")
        snippet = clean_text(item.get("snippet", ""))
        if not title or not link:
            continue
        articles.append(
            SourceArticle(
                title=title,
                summary=snippet,
                content=snippet,
                source_url=link,
                source_name="Google CSE",
                author="Google Search",
                published_at=None,
                image_url="",
                raw=item,
            )
        )
    return articles
