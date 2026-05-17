from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import sqlite3
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

import feedparser
import requests
import streamlit as st

try:
    import yaml
except ImportError:
    yaml = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:
    Request = None
    Credentials = None
    build = None

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None

try:
    from streamlit_ace import st_ace
except ImportError:
    st_ace = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SOURCES_FILE = BASE_DIR / "sources.yaml"
JSON_SOURCES_FILE = DATA_DIR / "sources.json"
DB_FILE = BASE_DIR / "history.db"
LOG_FILE = BASE_DIR / "autoblog.log"
DEFAULT_SEARX = "https://searx.be/search?format=json"
DB_LOCK = Lock()

DEFAULT_CONFIG = {
    "rss_feeds": [
        {
            "name": "CDC Travel Notices",
            "url": "https://wwwnc.cdc.gov/travel/rss/notices.xml",
            "enabled": True,
        },
        {
            "name": "CDC Newsroom",
            "url": "https://tools.cdc.gov/api/v2/resources/media/132608.rss",
            "enabled": True,
        },
        {
            "name": "WHO EMRO RSS directory",
            "url": "https://www.emro.who.int/rss-feeds.html",
            "enabled": True,
        },
        {
            "name": "Saudi MOH News generator",
            "url": "https://www.moh.gov.sa/_layouts/15/moh/RssGenerator.aspx?WebSiteUrl=/Ministry/MediaCenter/News/&ListUrl=/Ministry/MediaCenter/News/Pages/&ViewName=RSSView&RssTitle=&RssDescription=&DescriptionField=BriefDesc",
            "enabled": True,
        },
        {
            "name": "Saudi MOH Health Tips generator",
            "url": "https://www.moh.gov.sa/_layouts/15/moh/RssGenerator.aspx?WebSiteUrl=/HealthAwareness/EducationalContent/HealthTips/&ListUrl=/HealthAwareness/EducationalContent/HealthTips/Pages/&ViewName=RSSView&RssTitle=&RssDescription=BriefDesc",
            "enabled": True,
        },
        {
            "name": "Bahrain MOH Health Info",
            "url": "https://www.moh.gov.bh/HealthInfo/RSS",
            "enabled": True,
        },
        {
            "name": "Saudi SFDA Health News",
            "url": "https://www.sfda.gov.sa/ar/news.xml?tags=1",
            "enabled": True,
        },
    ],
    "keywords": [
        "علاج بالأعشاب",
        "فوائد صحية",
        "طب بديل",
        "الصحة في السعودية",
        "العناية الطبيعية",
    ],
    "blocked_keywords": [
        "معجزة",
        "شفاء نهائي",
        "علاج مضمون",
        "بدون طبيب",
    ],
    "searx_instance": DEFAULT_SEARX,
}

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("autoblog")
LOGGER.setLevel(logging.INFO)

file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
LOGGER.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
LOGGER.addHandler(console_handler)


def get_secret(key: str, default: str = "") -> str:
    if hasattr(st, "secrets") and isinstance(st.secrets, dict):
        value = st.secrets.get(key)
        if value:
            return str(value)
    return os.environ.get(key, default) or default


def ensure_data_directory() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def normalize_sources_config(config: dict) -> dict:
    if not isinstance(config, dict):
        return DEFAULT_CONFIG.copy()

    searx_instance = config.get(
        "searx_instance",
        config.get("default", {}).get("searx_instance", DEFAULT_SEARX),
    )

    if "sources" in config and isinstance(config["sources"], list):
        rss_feeds = []
        for source in config["sources"]:
            if not isinstance(source, dict):
                continue
            if str(source.get("type", "")).lower() != "rss":
                continue
            url = source.get("url")
            if not url:
                continue
            rss_feeds.append(
                {
                    "name": source.get("name") or source.get("id") or url,
                    "url": url,
                    "enabled": source.get("enabled", True),
                }
            )
        return {
            "rss_feeds": rss_feeds,
            "keywords": config.get("keywords", []),
            "blocked_keywords": config.get("blocked_keywords", []),
            "searx_instance": searx_instance,
        }

    return {
        "rss_feeds": config.get("rss_feeds", []),
        "keywords": config.get("keywords", []),
        "blocked_keywords": config.get("blocked_keywords", []),
        "searx_instance": searx_instance,
    }


def load_sources_config() -> dict:
    ensure_data_directory()
    if SOURCES_FILE.exists():
        text = SOURCES_FILE.read_text(encoding="utf-8")
        if yaml and not text.lstrip().startswith("{"):
            return yaml.safe_load(text) or DEFAULT_CONFIG
        return json.loads(text)
    if JSON_SOURCES_FILE.exists():
        try:
            config = json.loads(JSON_SOURCES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.exception("Invalid JSON in %s; using default source config", JSON_SOURCES_FILE)
            return DEFAULT_CONFIG.copy()
        return normalize_sources_config(config)
    save_sources_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_sources_config(config: dict) -> None:
    ensure_data_directory()
    if yaml:
        SOURCES_FILE.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    else:
        SOURCES_FILE.with_suffix(".json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def initialize_database() -> None:
    with DB_LOCK:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_urls (
                url TEXT PRIMARY KEY,
                title TEXT,
                source TEXT,
                last_seen TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS published_posts (
                url TEXT PRIMARY KEY,
                title TEXT,
                blog_post_id TEXT,
                published_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS fetch_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT,
                source_types TEXT,
                language TEXT,
                country TEXT,
                category TEXT,
                fetched_count INTEGER,
                published_count INTEGER,
                error TEXT
            )
            """
        )
        conn.commit()
        conn.close()


def execute_db(statement: str, params: tuple = (), fetch: bool = False):
    with DB_LOCK:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(statement, params)
        result = cursor.fetchall() if fetch else None
        if not fetch:
            conn.commit()
        conn.close()
        return result


def is_recently_seen(url: str, ttl_days: int) -> bool:
    row = execute_db("SELECT last_seen FROM seen_urls WHERE url = ?", (url,), fetch=True)
    if not row:
        return False
    last_seen = datetime.fromisoformat(row[0]["last_seen"])
    return datetime.utcnow() - last_seen < timedelta(days=ttl_days)


def mark_url_seen(url: str, title: str, source: str) -> None:
    execute_db(
        "INSERT OR REPLACE INTO seen_urls (url, title, source, last_seen) VALUES (?, ?, ?, ?)",
        (url, title, source, datetime.utcnow().isoformat()),
    )


def has_been_published(url: str) -> bool:
    row = execute_db("SELECT url FROM published_posts WHERE url = ?", (url,), fetch=True)
    return bool(row)


def record_published(url: str, title: str, blog_post_id: str) -> None:
    execute_db(
        "INSERT OR REPLACE INTO published_posts (url, title, blog_post_id, published_at) VALUES (?, ?, ?, ?)",
        (url, title, blog_post_id, datetime.utcnow().isoformat()),
    )


def clear_seen_history() -> None:
    execute_db("DELETE FROM seen_urls")


def record_fetch_run(
    source_types: str,
    language: str,
    country: str,
    category: str,
    fetched_count: int,
    published_count: int,
    error: str | None,
) -> None:
    execute_db(
        "INSERT INTO fetch_runs (run_at, source_types, language, country, category, fetched_count, published_count, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.utcnow().isoformat(),
            source_types,
            language,
            country,
            category,
            fetched_count,
            published_count,
            error,
        ),
    )


def get_last_fetch_summary() -> dict[str, str | int | None]:
    row = execute_db("SELECT * FROM fetch_runs ORDER BY run_at DESC LIMIT 1", fetch=True)
    if not row:
        return {}
    row = row[0]
    return {
        "last_fetch": row["run_at"],
        "last_source_types": row["source_types"],
        "last_language": row["language"],
        "last_country": row["country"],
        "last_category": row["category"],
        "last_fetched_count": row["fetched_count"],
        "last_published_count": row["published_count"],
        "last_error": row["error"],
    }


def get_published_today() -> int:
    today = datetime.utcnow().date().isoformat()
    rows = execute_db(
        "SELECT COUNT(*) as count FROM published_posts WHERE DATE(published_at) = ?", (today,), fetch=True
    )
    return int(rows[0]["count"]) if rows else 0


def fetch_rss_feed(feed_url: str, feed_name: str) -> list[dict]:
    LOGGER.info("Fetching RSS feed %s", feed_url)
    articles = []
    try:
        data = feedparser.parse(feed_url)
    except Exception:
        LOGGER.exception("RSS parse failure for %s", feed_url)
        return []

    for entry in data.entries[:30]:
        url = entry.get("link") or entry.get("id")
        if not url:
            continue
        title = entry.get("title", "Untitled").strip()
        summary = entry.get("summary") or entry.get("description") or ""
        image = None
        media_content = entry.get("media_content") or entry.get("media_thumbnail")
        if media_content:
            if isinstance(media_content, list):
                image = media_content[0].get("url")
            elif isinstance(media_content, dict):
                image = media_content.get("url")
        published = entry.get("published") or entry.get("updated") or ""
        articles.append(
            {
                "title": title,
                "url": url,
                "summary": summary,
                "content": summary,
                "image": image,
                "source": feed_name,
                "published": published,
            }
        )
    return articles


def discover_who_emro_feeds(page_url: str) -> list[dict]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        response = requests.get(page_url, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
        candidates = set(re.findall(r"href=[\"']([^\"']+\.(?:xml|rss)(?:\?[^\"']*)?)[\"']", html, re.I))
        candidates.update(re.findall(r"<link[^>]+href=[\"']([^\"']+)[\"'][^>]+type=[\"']application/rss\+xml[\"']", html, re.I))
        urls = []
        for candidate in candidates:
            if not candidate.startswith("http"):
                candidate = requests.compat.urljoin(page_url, candidate)
            urls.append(candidate)
        return [{"name": f"WHO EMRO feed {i + 1}", "url": url, "enabled": True} for i, url in enumerate(urls)]
    except Exception:
        LOGGER.exception("Failed to discover WHO EMRO feeds")
        return []


def fetch_rss_sources(config: dict) -> list[dict]:
    articles = []
    for feed in config.get("rss_feeds", []):
        if not feed.get("enabled", True):
            continue
        url = str(feed.get("url", "")).strip()
        name = str(feed.get("name", url)).strip()
        if not url:
            continue
        if "emro.who.int/rss-feeds.html" in url:
            discovered = discover_who_emro_feeds(url)
            for child in discovered:
                articles.extend(fetch_rss_feed(child["url"], child["name"]))
        else:
            articles.extend(fetch_rss_feed(url, name))
    LOGGER.info("RSS source returned %d articles", len(articles))
    return articles


def fetch_currents_api(language: str, country: str, category: str) -> list[dict]:
    api_key = get_secret("CURRENTS_API_KEY")
    if not api_key:
        LOGGER.warning("Currents API key not configured")
        return []
    endpoint = "https://api.currentsapi.services/v1/latest-news"
    params = {
        "language": language,
        "country": country,
        "category": category,
        "apiKey": api_key,
        "page_size": 20,
    }
    try:
        response = requests.get(endpoint, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        items = data.get("news", [])
        articles = []
        for item in items:
            articles.append(
                {
                    "title": item.get("title", "Untitled").strip(),
                    "url": item.get("url"),
                    "summary": item.get("description", ""),
                    "content": item.get("description", ""),
                    "image": item.get("image"),
                    "source": item.get("source", {}).get("name", "Currents API") if isinstance(item.get("source"), dict) else item.get("source", "Currents API"),
                    "published": item.get("published", ""),
                }
            )
        LOGGER.info("Currents returned %d articles", len(articles))
        return [article for article in articles if article.get("url")]
    except Exception:
        LOGGER.exception("Currents API fetch failed")
        return []


def fetch_google_cse(query: str, limit: int = 10) -> list[dict]:
    api_key = get_secret("GOOGLE_CSE_API_KEY")
    engine_id = get_secret("GOOGLE_CSE_ENGINE_ID")
    if not api_key or not engine_id:
        return []
    endpoint = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": engine_id, "q": query, "num": min(limit, 10)}
    try:
        response = requests.get(endpoint, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        results = data.get("items", [])
        articles = []
        for item in results:
            articles.append(
                {
                    "title": item.get("title", "Untitled"),
                    "url": item.get("link"),
                    "summary": item.get("snippet", ""),
                    "content": item.get("snippet", ""),
                    "image": None,
                    "source": item.get("displayLink", "Google CSE"),
                    "published": "",
                }
            )
        LOGGER.info("Google CSE returned %d fallback articles", len(articles))
        return articles
    except Exception:
        LOGGER.exception("Google CSE fallback failed")
        return []


def fetch_deep_search(language: str, config: dict, target_count: int = 10) -> list[dict]:
    query = "أخبار الصحة" if language == "ar" else f"latest health news {datetime.utcnow().date().isoformat()}"
    searx_instance = config.get("searx_instance", DEFAULT_SEARX)
    articles = []
    try:
        response = requests.get(searx_instance, params={"q": query, "format": "json"}, timeout=20)
        response.raise_for_status()
        data = response.json()
        for item in data.get("results", [])[:target_count]:
            articles.append(
                {
                    "title": item.get("title", "Untitled"),
                    "url": item.get("url"),
                    "summary": item.get("content", ""),
                    "content": item.get("content", ""),
                    "image": None,
                    "source": item.get("engine", "SearxNG"),
                    "published": item.get("published", ""),
                }
            )
    except Exception:
        LOGGER.exception("Deep search fallback with SearxNG failed")
    if len(articles) < target_count:
        articles.extend(fetch_google_cse(query, limit=target_count - len(articles)))
    deduped = []
    seen = set()
    for article in articles:
        if not article.get("url"):
            continue
        if article["url"] in seen:
            continue
        seen.add(article["url"])
        deduped.append(article)
    LOGGER.info("Deep search fallback returned %d articles", len(deduped))
    return deduped[:target_count]


def dedupe_articles(articles: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for article in articles:
        url = article.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(article)
    return deduped


def gemini_generate(prompt: str) -> str:
    api_key = get_secret("GEMINI_API_KEY")
    if not genai or not api_key:
        raise RuntimeError("Google Gemini is not configured or the package is unavailable.")
    genai.configure(api_key=api_key)
    response = genai.generate_text(
        model="gemini-1.0",
        prompt=prompt,
        temperature=0.2,
        max_output_tokens=512,
    )
    if isinstance(response, dict):
        candidates = response.get("candidates") or []
        if candidates and isinstance(candidates, list):
            return str(candidates[0].get("content", "")).strip()
        return str(response.get("content", "")).strip()
    return str(response)


def enhance_article(article: dict, mode: str, target_language: str) -> str:
    source_text = article.get("content") or article.get("summary") or article.get("title")
    if mode == "None" or not source_text:
        return source_text

    if mode == "Summary":
        prompt = f"""Summarize the following health news article in 2-3 sentences in {target_language}. """
        prompt += f"""

Keep the wording clear and professional.

Article:
{source_text}

Source URL: {article.get('url')}"""
    elif mode == "Rewrite":
        prompt = f"""Rewrite the following health news text into an engaging, SEO-friendly blog post in {target_language}. """
        prompt += f"""

Keep the facts, add a professional tone, and preserve the meaning.

Include a short introduction, body paragraphs, and a source note at the end.

Article:
{source_text}

Source URL: {article.get('url')}"""
    else:
        prompt = f"""Translate the following health news text into {target_language}. """
        prompt += f"""

Keep the meaning accurate and use natural language.

Article:
{source_text}

Source URL: {article.get('url')}"""

    try:
        return gemini_generate(prompt)
    except Exception:
        LOGGER.exception("Gemini enhancement failed")
        return source_text


def build_post_html(article: dict, enhanced_body: str) -> str:
    parts = [f"<h2>{article.get('title', 'Health Article')}</h2>"]
    if article.get("image"):
        parts.append(
            f'<div><img src="{article["image"]}" alt="{article["title"]}" style="max-width:100%;height:auto;"/></div>'
        )
    parts.append(f"<p><em>Source: {article.get('source', 'Unknown')}</em></p>")
    parts.append(f"<div>{enhanced_body}</div>")
    parts.append(
        f'<p><strong>Original source:</strong> <a href="{article.get("url")}" target="_blank">{article.get("url")}</a></p>'
    )
    return "".join(parts)


def get_blogger_service() -> object:
    if not (Credentials and Request and build):
        raise RuntimeError("Google Blogger client libraries are not installed.")
    client_id = get_secret("BLOGGER_CLIENT_ID")
    client_secret = get_secret("BLOGGER_CLIENT_SECRET")
    refresh_token = get_secret("BLOGGER_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError("Blogger OAuth credentials are missing.")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/blogger"],
    )
    if not creds.valid:
        creds.refresh(Request())
    return build("blogger", "v3", credentials=creds)


def publish_to_blogger(article: dict, html_body: str, labels: list[str], as_draft: bool) -> dict:
    blog_id = get_secret("BLOG_ID")
    if not blog_id:
        raise RuntimeError("BLOG_ID is not configured.")
    service = get_blogger_service()
    post_body = {
        "kind": "blogger#post",
        "blog": {"id": blog_id},
        "title": article.get("title", "Health Update"),
        "content": html_body,
        "labels": labels,
    }
    request = service.posts().insert(blogId=blog_id, body=post_body, isDraft=as_draft)
    return request.execute()


def build_labels(category: str, article: dict) -> list[str]:
    labels = [category.capitalize()] if category else []
    if article.get("source"):
        labels.append(article["source"])
    labels.append("Health")
    return [label for label in dict.fromkeys(labels) if label]


def run_cycle(
    source_types: list[str],
    language: str,
    country: str,
    category: str,
    history_ttl: int,
    max_posts: int,
    enhance_mode: str,
    publish_as_draft: bool,
    min_fallback: int,
) -> dict:
    config = load_sources_config()
    articles = []
    if "RSS Feeds" in source_types:
        articles.extend(fetch_rss_sources(config))
    if "Currents API" in source_types:
        articles.extend(fetch_currents_api(language, country, category))
    articles = dedupe_articles(articles)
    if len(articles) < min_fallback and "Deep Search Fallback" in source_types:
        articles.extend(fetch_deep_search(language, config, target_count=min_fallback))
    articles = dedupe_articles(articles)

    filtered = []
    for article in articles:
        if not article.get("url"):
            continue
        if is_recently_seen(article["url"], history_ttl):
            continue
        filtered.append(article)

    published_count = 0
    results = []
    for article in filtered[:max_posts]:
        try:
            enhanced_body = enhance_article(article, enhance_mode, language)
            html_body = build_post_html(article, enhanced_body)
            labels = build_labels(category, article)
            blog_result = publish_to_blogger(article, html_body, labels, as_draft=publish_as_draft)
            record_published(article["url"], article["title"], blog_result.get("id", ""))
            LOGGER.info("Published article %s", article["url"])
            results.append({"article": article, "published": True, "post_url": blog_result.get("url")})
            published_count += 1
        except Exception:
            LOGGER.exception("Failed to publish article %s", article.get("url"))
            results.append({"article": article, "published": False, "error": traceback.format_exc()})
        finally:
            mark_url_seen(article["url"], article.get("title", ""), article.get("source", ""))

    record_fetch_run(
        source_types=", ".join(source_types),
        language=language,
        country=country,
        category=category,
        fetched_count=len(articles),
        published_count=published_count,
        error=None,
    )

    return {
        "requested_sources": source_types,
        "language": language,
        "country": country,
        "category": category,
        "fetched_count": len(articles),
        "published_count": published_count,
        "results": results,
    }


@st.cache_resource
def get_scheduler() -> object | None:
    if BackgroundScheduler is None:
        return None
    scheduler = BackgroundScheduler()
    scheduler.start()
    return scheduler


def schedule_background_job(
    enabled: bool,
    interval_hours: int,
    source_types: list[str],
    language: str,
    country: str,
    category: str,
    history_ttl: int,
    max_posts: int,
    enhance_mode: str,
    publish_as_draft: bool,
    min_fallback: int,
) -> None:
    scheduler = get_scheduler()
    if scheduler is None:
        return
    job_id = "autoblog_scheduler_job"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if not enabled:
        return
    scheduler.add_job(
        run_cycle,
        "interval",
        hours=interval_hours,
        id=job_id,
        args=[
            source_types,
            language,
            country,
            category,
            history_ttl,
            max_posts,
            enhance_mode,
            publish_as_draft,
            min_fallback,
        ],
        replace_existing=True,
    )
    LOGGER.info("Auto scheduler enabled: every %d hours", interval_hours)


def format_datetime(timestamp: str | None) -> str:
    if not timestamp:
        return "Never"
    try:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return timestamp


def main() -> None:
    st.set_page_config(
        page_title="Auto Health Blog Agent",
        page_icon="📰",
        layout="wide",
    )
    st.title("🧠 Auto Health Blog Agent")
    st.write(
        "A self-contained Streamlit dashboard that fetches health news, enhances content with Gemini, "
        "and publishes posts to Blogger automatically."
    )

    initialize_database()
    config = load_sources_config()
    last_summary = get_last_fetch_summary()

    if "latest_articles" not in st.session_state:
        st.session_state["latest_articles"] = []
    if "last_cycle" not in st.session_state:
        st.session_state["last_cycle"] = {}
    if "auto_scheduler_enabled" not in st.session_state:
        st.session_state["auto_scheduler_enabled"] = True
    if "scheduler_interval" not in st.session_state:
        st.session_state["scheduler_interval"] = 24
    if "max_posts_per_cycle" not in st.session_state:
        st.session_state["max_posts_per_cycle"] = 1

    with st.sidebar:
        st.header("Fetch & automation")
        source_types = st.multiselect(
            "Select active source types",
            ["RSS Feeds", "Currents API", "Deep Search Fallback"],
            default=["RSS Feeds", "Currents API"],
        )
        if not source_types:
            st.warning("Please choose at least one active source type.")

        language = st.selectbox("Language", ["ar", "en"], index=0)
        country = st.selectbox("Country", ["sa", "us", "eg", "ae", "gb", "all"], index=0)
        category = st.selectbox("Category", ["health", "science", "general"], index=0)
        history_ttl = st.number_input(
            "History TTL (days)",
            min_value=1,
            max_value=365,
            value=30,
            help="Articles are considered new again after this number of days.",
        )
        st.button("Clear Seen History", on_click=clear_seen_history)

        st.markdown("---")
        st.subheader("Auto scheduling")
        st.session_state["auto_scheduler_enabled"] = st.checkbox(
            "Enable auto-scheduler",
            value=st.session_state["auto_scheduler_enabled"],
        )
        st.session_state["scheduler_interval"] = st.number_input(
            "Scheduler interval (hours)",
            min_value=1,
            max_value=168,
            value=st.session_state["scheduler_interval"],
        )
        st.session_state["max_posts_per_cycle"] = st.number_input(
            "Max posts per run",
            min_value=1,
            max_value=10,
            value=st.session_state["max_posts_per_cycle"],
        )
        publish_as_draft = st.checkbox("Publish as draft", value=True)
        enhance_mode = st.radio(
            "Enhancement mode",
            ["Summary", "Rewrite", "Translate", "None"],
            index=1,
        )
        min_fallback = st.number_input(
            "Deep search fallback threshold",
            min_value=1,
            max_value=20,
            value=5,
            help="If fewer than this number of articles are available, fall back to search.",
        )
        st.markdown("---")
        fetch_now = st.button("Fetch Now")
        st.write(
            "Use Fetch Now to run a full fetch, enhance, and publish cycle immediately. "
            "The scheduler will continue to run in the background if enabled."
        )

    schedule_background_job(
        enabled=st.session_state["auto_scheduler_enabled"],
        interval_hours=st.session_state["scheduler_interval"],
        source_types=source_types,
        language=language,
        country=country,
        category=category,
        history_ttl=history_ttl,
        max_posts=st.session_state["max_posts_per_cycle"],
        enhance_mode=enhance_mode,
        publish_as_draft=publish_as_draft,
        min_fallback=min_fallback,
    )

    blogger_ready = all(
        [get_secret("BLOGGER_CLIENT_ID"), get_secret("BLOGGER_CLIENT_SECRET"), get_secret("BLOGGER_REFRESH_TOKEN"), get_secret("BLOG_ID")]
    )
    currents_ready = bool(get_secret("CURRENTS_API_KEY"))
    gemini_ready = bool(get_secret("GEMINI_API_KEY")) and genai is not None

    if "Currents API" in source_types and not currents_ready:
        st.sidebar.warning("Currents API selected but CURRENTS_API_KEY is missing.")
    if not blogger_ready:
        st.sidebar.warning("Blogger credentials are not fully configured. Publishing will fail until the secrets are set.")
    if enhance_mode != "None" and not gemini_ready:
        st.sidebar.warning("Gemini not available. Enhancement will fall back to raw content.")

    if fetch_now and source_types:
        with st.spinner("Running fetch, enhancement and publish cycle…"):
            try:
                summary = run_cycle(
                    source_types=source_types,
                    language=language,
                    country=country,
                    category=category,
                    history_ttl=history_ttl,
                    max_posts=st.session_state["max_posts_per_cycle"],
                    enhance_mode=enhance_mode,
                    publish_as_draft=publish_as_draft,
                    min_fallback=min_fallback,
                )
                st.session_state["last_cycle"] = summary
                st.session_state["latest_articles"] = [result["article"] for result in summary["results"]]
                st.success(
                    f"Fetched {summary['fetched_count']} articles and published {summary['published_count']} posts."
                )
            except Exception as exc:
                LOGGER.exception("Fetch now cycle failure")
                st.error(f"Fetch cycle failed: {exc}")

    row1, row2, row3, row4 = st.columns(4)
    row1.metric("Last fetch", format_datetime(last_summary.get("last_fetch")))
    row2.metric("Articles last cycle", last_summary.get("last_fetched_count", 0))
    row3.metric("Published today", get_published_today())
    row4.metric("Scheduler status", "Running" if st.session_state["auto_scheduler_enabled"] else "Stopped")

    if last_summary.get("last_error"):
        st.error(f"Last run error: {last_summary['last_error']}")

    tabs = st.tabs(["Overview", "Sources", "Preview", "Logs"])

    with tabs[0]:
        st.subheader("Overview")
        st.markdown(
            "This dashboard uses RSS feeds, Currents API, and a deep search fallback to keep your health blog active. "
            "Configure sources and scheduling from the sidebar."
        )
        st.write("### Active sources")
        st.write(", ".join(source_types) if source_types else "None selected")
        st.write("### Current configuration")
        st.write(f"Language: {language}, Country: {country}, Category: {category}")
        st.write(f"Auto scheduler interval: {st.session_state['scheduler_interval']} hours")
        st.write(f"Enhancement mode: {enhance_mode}")
        st.write(f"Publishing as draft: {publish_as_draft}")

    with tabs[1]:
        st.subheader("Source configuration")
        st.write(
            "Edit active RSS sources and feed configuration. Your changes are stored in `sources.yaml`. "
            "You can add or remove feeds and update the Searx instance URL."
        )
        config_editor = json.dumps(config, ensure_ascii=False, indent=2)
        if st_ace:
            user_config = st_ace(
                value=config_editor,
                language="json",
                theme="monokai",
                height=360,
                key="source_editor",
            )
        else:
            user_config = st.text_area("Edit source configuration", value=config_editor, height=360)
        if st.button("Save source configuration"):
            try:
                new_config = json.loads(user_config)
                save_sources_config(new_config)
                st.success("Source configuration saved.")
                config = new_config
            except Exception as exc:
                st.error(f"Unable to save configuration: {exc}")

        if st.checkbox("Show configured RSS feeds", value=True):
            feeds = config.get("rss_feeds", [])
            if feeds:
                st.dataframe(feeds)
            else:
                st.info("No RSS feeds are configured.")

    with tabs[2]:
        st.subheader("Preview latest fetched articles")
        latest = st.session_state.get("latest_articles", [])
        if latest:
            preview_rows = []
            for article in latest[:5]:
                preview_rows.append(
                    {
                        "title": article.get("title"),
                        "source": article.get("source"),
                        "url": article.get("url"),
                        "published": article.get("published"),
                    }
                )
            st.dataframe(preview_rows)
            for article in latest[:5]:
                st.markdown(f"### {article.get('title')}")
                st.write(f"Source: {article.get('source')}")
                st.write(f"URL: {article.get('url')}")
                st.write(article.get("summary"))
        else:
            st.info("No articles fetched yet. Click Fetch Now to start a cycle.")

    with tabs[3]:
        st.subheader("Logs")
        if LOG_FILE.exists():
            log_text = LOG_FILE.read_text(encoding="utf-8")
            lines = log_text.splitlines()[-200:]
            st.code("\n".join(lines))
        else:
            st.info("Log file not found yet.")

    st.markdown("---")
    st.write(
        "Your app is ready to run with `streamlit run app.py`. Ensure `CURRENTS_API_KEY`, "
        "`GEMINI_API_KEY`, `BLOGGER_CLIENT_ID`, `BLOGGER_CLIENT_SECRET`, `BLOGGER_REFRESH_TOKEN`, and `BLOG_ID` are configured in Streamlit secrets or environment variables."
    )


if __name__ == "__main__":
    main()
