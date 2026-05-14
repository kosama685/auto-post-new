from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import SourceArticle
from .utils import clean_text, parse_datetime

USER_AGENT = "ArabicHerbalNewsBot/1.0 (+reviewed content; contact: site owner)"


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


def fetch_currents_api(
    api_key: str,
    keywords: list[str] | None = None,
    language: str = "ar",
    country: str = "",
    category: str = "health",
    limit: int = 10,
) -> list[SourceArticle]:
    if not api_key:
        return []

    query = " OR ".join([clean_text(keyword) for keyword in (keywords or [])][:5]) or "health"
    params = {
        "apiKey": api_key,
        "language": language,
        "category": category,
        "page_size": min(max(limit, 1), 20),
    }
    if country:
        params["country"] = country
    if query:
        params["keywords"] = query

    response = _get("https://api.currentsapi.services/v1/latest-news", params=params)
    payload = response.json()
    articles: list[SourceArticle] = []

    for item in payload.get("news", [])[:limit]:
        title = clean_text(item.get("title", ""))
        url = item.get("url", "")
        if not title or not url:
            continue
        articles.append(
            SourceArticle(
                title=title,
                summary=clean_text(item.get("description", "")),
                content=clean_text(item.get("description", "")),
                source_url=url,
                source_name="Currents API",
                author=clean_text(item.get("author", "Unknown")) or "Unknown",
                published_at=parse_datetime(item.get("published", None)) or datetime.now(timezone.utc),
                image_url=item.get("image") or "",
                raw=item,
            )
        )
    return articles


def fetch_gnews_api(
    api_key: str,
    keywords: list[str] | None = None,
    language: str = "ar",
    country: str = "",
    category: str = "health",
    limit: int = 10,
) -> list[SourceArticle]:
    if not api_key:
        return []

    query = " OR ".join([clean_text(keyword) for keyword in (keywords or [])][:5]) or "health"
    params = {
        "token": api_key,
        "q": query,
        "lang": language,
        "max": min(max(limit, 1), 10),
    }
    if country:
        params["country"] = country
    if category:
        params["topic"] = category

    response = _get("https://gnews.io/api/v4/search", params=params)
    payload = response.json()
    articles: list[SourceArticle] = []

    for item in payload.get("articles", [])[:limit]:
        title = clean_text(item.get("title", ""))
        url = item.get("url", "")
        if not title or not url:
            continue
        articles.append(
            SourceArticle(
                title=title,
                summary=clean_text(item.get("description", "")),
                content=clean_text(item.get("content", "")),
                source_url=url,
                source_name=(item.get("source") or {}).get("name", "GNews API"),
                author=clean_text(item.get("author", "Unknown")) or "Unknown",
                published_at=parse_datetime(item.get("publishedAt", None)) or datetime.now(timezone.utc),
                image_url=item.get("image", ""),
                raw=item,
            )
        )
    return articles
