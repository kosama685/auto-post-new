from __future__ import annotations

import time
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import get_settings, load_sources
from .logger_setup import logger
from .models import SourceArticle
from .utils import clean_text, parse_datetime

USER_AGENT = "ArabicHerbalBlogBot/1.0 (+reviewed content; contact: site owner)"


def _can_fetch(url: str) -> bool:
    """Best-effort robots.txt check for non-RSS article pages."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        # If robots.txt cannot be read, do not block RSS summary use.
        return True


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
def _get(url: str, params: dict | None = None) -> requests.Response:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"},
        timeout=20,
    )
    response.raise_for_status()
    return response


def fetch_from_rss(limit_per_source: int | None = None) -> list[SourceArticle]:
    settings = get_settings()
    sources = load_sources()
    limit = limit_per_source or settings.fetch_limit_per_source
    articles: list[SourceArticle] = []

    for feed in sources.get("rss_feeds", []):
        if not feed.get("enabled", True):
            continue
        feed_url = feed.get("url", "").strip()
        if not feed_url:
            continue
        source_name = feed.get("name") or urlparse(feed_url).netloc
        try:
            logger.info("Fetching RSS feed: %s", feed_url)
            parsed = feedparser.parse(feed_url, request_headers={"User-Agent": USER_AGENT})
            for entry in parsed.entries[:limit]:
                title = clean_text(getattr(entry, "title", ""))
                link = getattr(entry, "link", "").strip()
                if not title or not link:
                    continue
                summary = clean_text(getattr(entry, "summary", "") or getattr(entry, "description", ""))
                author = clean_text(getattr(entry, "author", "Unknown")) or "Unknown"
                published = parse_datetime(getattr(entry, "published", None) or getattr(entry, "updated", None))
                image_url = ""
                media_content = getattr(entry, "media_content", None) or []
                if media_content and isinstance(media_content, list):
                    image_url = media_content[0].get("url", "")
                articles.append(
                    SourceArticle(
                        title=title,
                        summary=summary,
                        source_url=link,
                        source_name=source_name,
                        author=author,
                        published_at=published,
                        image_url=image_url,
                        raw={"feed": feed_url},
                    )
                )
            time.sleep(settings.request_delay_seconds)
        except Exception as exc:
            logger.exception("Failed to fetch RSS %s: %s", feed_url, exc)
    return articles


def fetch_from_newsapi(limit: int | None = None) -> list[SourceArticle]:
    settings = get_settings()
    if not settings.newsapi_key:
        return []
    sources = load_sources()
    keywords = sources.get("keywords", []) or ["الصحة"]
    page_size = limit or settings.newsapi_page_size
    params = {
        "q": " OR ".join(keywords[:5]),
        "language": settings.newsapi_language,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": settings.newsapi_key,
    }
    try:
        logger.info("Fetching NewsAPI articles")
        response = _get("https://newsapi.org/v2/everything", params=params)
        payload = response.json()
        result: list[SourceArticle] = []
        for item in payload.get("articles", []):
            title = clean_text(item.get("title", ""))
            url = item.get("url", "")
            if not title or not url:
                continue
            result.append(
                SourceArticle(
                    title=title,
                    summary=clean_text(item.get("description", "")),
                    content=clean_text(item.get("content", "")),
                    source_url=url,
                    source_name=(item.get("source") or {}).get("name", "NewsAPI"),
                    author=clean_text(item.get("author", "Unknown")) or "Unknown",
                    published_at=parse_datetime(item.get("publishedAt")) or datetime.now(timezone.utc),
                    image_url=item.get("urlToImage") or "",
                    raw=item,
                )
            )
        return result
    except Exception as exc:
        logger.exception("Failed to fetch NewsAPI: %s", exc)
        return []


def fetch_articles(include_newsapi: bool = True, limit_per_source: int | None = None) -> list[SourceArticle]:
    articles = fetch_from_rss(limit_per_source=limit_per_source)
    if include_newsapi:
        articles.extend(fetch_from_newsapi(limit=limit_per_source))

    unique: dict[str, SourceArticle] = {}
    for article in articles:
        if not article.source_url:
            continue
        if not _can_fetch(article.source_url):
            logger.warning("Robots blocked article URL, skipping: %s", article.source_url)
            continue
        unique[article.source_url] = article
    return list(unique.values())
