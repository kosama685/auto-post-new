from __future__ import annotations

import time
import urllib.robotparser
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import get_settings
from .deep_search import search_google_cse, search_searxng
from .logger_setup import logger
from .models import SourceArticle
from .news_api_fetcher import fetch_currents_api, fetch_gnews_api
from .source_manager import (
    get_active_sources,
    get_blocked_keywords,
    get_default_fetch_parameters,
    get_keywords,
    get_source_api_key,
    normalize_source,
)
from .storage import Storage
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


def _extract_rss_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()

    for tag in soup.find_all(["link", "a"], href=True):
        href = tag["href"].strip()
        if not href:
            continue
        if any(token in href.lower() for token in [".rss", ".xml", "feed", "mediarss", "rssgenerator.aspx"]):
            urls.add(urljoin(base_url, href))

    for tag in soup.find_all("link", rel=lambda value: value and "alternate" in value, href=True):
        href = tag["href"].strip()
        if href and any(token in href.lower() for token in ["rss", "xml", "atom"]):
            urls.add(urljoin(base_url, href))

    return list(urls)


def _resolve_feed_urls(feed_url: str) -> list[str]:
    try:
        response = _get(feed_url)
        content_type = response.headers.get("Content-Type", "")
        if "html" in content_type.lower() or "<html" in response.text.lower():
            return _extract_rss_links(response.text, response.url) or [feed_url]
        return [feed_url]
    except Exception as exc:
        logger.warning("Unable to resolve RSS index page %s: %s", feed_url, exc)
        return [feed_url]


def _fetch_rss_source(source: dict[str, Any], limit: int) -> list[SourceArticle]:
    url = source.get("url", "").strip()
    source_id = source.get("id") or source.get("name") or url
    source_name = source.get("name") or urlparse(url).netloc
    articles: list[SourceArticle] = []
    if not url:
        return []

    logger.info("Fetching RSS source: %s", url)
    resolved_urls = _resolve_feed_urls(url)
    if not resolved_urls:
        resolved_urls = [url]

    fetched = 0
    error: str | None = None
    for resolved_url in resolved_urls[:5]:
        try:
            logger.info("Parsing RSS feed: %s", resolved_url)
            response = _get(resolved_url)
            parsed = feedparser.parse(response.content)
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
                        raw={"feed": resolved_url},
                    )
                )
            fetched += len(articles)
        except Exception as exc:
            error = str(exc)
            logger.warning("Failed to parse RSS feed %s: %s", resolved_url, exc)
    Storage().log_fetch_run(
        source_id=source_id,
        source_name=source_name,
        source_type="rss",
        source_url=url,
        success=bool(articles),
        item_count=len(articles),
        error=error,
    )
    return articles


def _fetch_api_source(
    source: dict[str, Any],
    keywords: list[str],
    language: str,
    country: str,
    category: str,
    limit: int,
) -> list[SourceArticle]:
    source = normalize_source(source)
    source_id = source.get("id") or source.get("name")
    source_name = source.get("name") or source.get("type")
    source_type = source.get("type")
    api_key = get_source_api_key(source)
    articles: list[SourceArticle] = []

    try:
        if source_type == "currents_api":
            articles = fetch_currents_api(
                api_key=api_key,
                keywords=keywords,
                language=source.get("language") or language,
                country=source.get("country") or country,
                category=source.get("category") or category,
                limit=source.get("limit") or limit,
            )
        elif source_type == "gnews_api":
            articles = fetch_gnews_api(
                api_key=api_key,
                keywords=keywords,
                language=source.get("language") or language,
                country=source.get("country") or country,
                category=source.get("category") or category,
                limit=source.get("limit") or limit,
            )
        else:
            logger.warning("Unknown API source type: %s", source_type)
    except Exception as exc:
        logger.warning("Failed to fetch API source %s: %s", source_name, exc)
        Storage().log_fetch_run(
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            source_url=source.get("url", ""),
            success=False,
            item_count=0,
            error=str(exc),
        )
        return []

    Storage().log_fetch_run(
        source_id=source_id,
        source_name=source_name,
        source_type=source_type,
        source_url=source.get("url", ""),
        success=bool(articles),
        item_count=len(articles),
        error=None,
    )
    return articles


def _fetch_searx_source(
    source: dict[str, Any],
    keywords: list[str],
    language: str,
    limit: int,
) -> list[SourceArticle]:
    source_id = source.get("id") or source.get("name")
    source_name = source.get("name") or "SearxNG"
    query_template = source.get("query_template") or "{keyword} health news"
    instance_url = source.get("instance_url") or get_default_fetch_parameters().get("searx_instance", "https://searx.be")
    results: list[SourceArticle] = []
    error: str | None = None

    for keyword in keywords[:3] or ["health"]:
        try:
            query = query_template.format(keyword=keyword)
            results.extend(
                search_searxng(
                    query=query,
                    instance_url=instance_url,
                    language=language,
                    limit=min(limit, 10),
                )
            )
            if len(results) >= limit:
                break
        except Exception as exc:
            error = str(exc)
            logger.warning("SearxNG search failed for %s: %s", query, exc)
            break

    Storage().log_fetch_run(
        source_id=source_id,
        source_name=source_name,
        source_type="searxng",
        source_url=instance_url,
        success=bool(results),
        item_count=len(results),
        error=error,
    )
    return results[:limit]


def _normalize_articles(articles: list[SourceArticle]) -> list[SourceArticle]:
    unique: dict[str, SourceArticle] = {}
    for article in articles:
        if not article.source_url:
            continue
        if not _can_fetch(article.source_url):
            logger.warning("Robots blocked article URL, skipping: %s", article.source_url)
            continue
        unique[article.source_url] = article
    return list(unique.values())


def _deep_search_fallback(
    current_count: int,
    minimum: int,
    language: str,
    keywords: list[str],
    limit: int,
) -> list[SourceArticle]:
    if current_count >= minimum:
        return []
    logger.info("Triggering deep search fallback: current_count=%s minimum=%s", current_count, minimum)
    results: list[SourceArticle] = []
    for keyword in keywords[:3] or ["health"]:
        query = f"{keyword} health news"
        results.extend(search_searxng(query=query, language=language, limit=min(limit, 10)))
        if len(results) >= minimum:
            break
    return results[: max(minimum - current_count, 0)]


def fetch_from_rss(limit_per_source: int | None = None) -> list[SourceArticle]:
    settings = get_settings()
    limit = limit_per_source or settings.fetch_limit_per_source
    articles: list[SourceArticle] = []
    for feed in get_active_sources("rss"):
        articles.extend(_fetch_rss_source(feed, limit))
    return articles


def fetch_from_newsapi(limit: int | None = None) -> list[SourceArticle]:
    settings = get_settings()
    if not settings.newsapi_key:
        return []
    sources = get_active_sources("newsapi")
    keywords = get_keywords() or ["الصحة"]
    page_size = limit or settings.newsapi_page_size
    if not sources:
        return []
    articles: list[SourceArticle] = []
    for source in sources:
        articles.extend(_fetch_api_source(source, keywords, settings.newsapi_language, settings.newsapi_country, settings.newsapi_category, page_size))
    return articles


def fetch_articles(
    source_type: str = "both",
    language: str = "ar",
    country: str = "",
    category: str = "health",
    limit_per_source: int | None = None,
    deep_search_minimum: int | None = None,
    include_newsapi: bool = False,
) -> list[SourceArticle]:
    settings = get_settings()
    limit = limit_per_source or settings.fetch_limit_per_source
    deep_minimum = deep_search_minimum if deep_search_minimum is not None else get_default_fetch_parameters().get("deep_search_minimum", 5)
    keywords = get_keywords() or ["health"]
    articles: list[SourceArticle] = []

    if source_type in {"rss", "both"}:
        articles.extend(fetch_from_rss(limit_per_source=limit))

    if source_type in {"currents", "both"}:
        for source in get_active_sources("currents_api"):
            articles.extend(_fetch_api_source(source, keywords, language, country, category, limit))

    if source_type in {"gnews", "both"}:
        for source in get_active_sources("gnews_api"):
            articles.extend(_fetch_api_source(source, keywords, language, country, category, limit))

    if source_type in {"searxng", "both"}:
        for source in get_active_sources("searxng"):
            articles.extend(_fetch_searx_source(source, keywords, language, limit))

    if include_newsapi:
        articles.extend(fetch_from_newsapi(limit=limit))

    unique_articles = _normalize_articles(articles)
    if len(unique_articles) < deep_minimum:
        fallback = _deep_search_fallback(len(unique_articles), deep_minimum, language, keywords, limit)
        unique_articles.extend(_normalize_articles(fallback))

    return _normalize_articles(unique_articles)
