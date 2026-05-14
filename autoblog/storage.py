from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import get_settings
from .models import GeneratedPost, PublishResult, SourceArticle
from .utils import source_hash


class Storage:
    def __init__(self, db_path: Path | None = None) -> None:
        self.settings = get_settings()
        self.db_path = db_path or self.settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL UNIQUE,
                    source_hash TEXT NOT NULL UNIQUE,
                    source_name TEXT,
                    author TEXT,
                    published_at TEXT,
                    fetched_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'fetched'
                );
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    slug TEXT,
                    meta_description TEXT,
                    labels TEXT,
                    html TEXT,
                    platform TEXT,
                    platform_post_id TEXT,
                    platform_url TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    published_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
                CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
                """
            )

    def article_exists(self, article: SourceArticle) -> bool:
        h = source_hash(article.source_url, article.title)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM articles WHERE source_hash = ? OR source_url = ? LIMIT 1",
                (h, article.source_url),
            ).fetchone()
            return row is not None

    def save_article(self, article: SourceArticle, status: str = "fetched") -> None:
        h = source_hash(article.source_url, article.title)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO articles
                (title, source_url, source_hash, source_name, author, published_at, fetched_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.title,
                    article.source_url,
                    h,
                    article.source_name,
                    article.author,
                    article.normalized_publish_date(),
                    datetime.now(timezone.utc).isoformat(),
                    status,
                ),
            )

    def save_post(self, post: GeneratedPost, result: PublishResult | None = None) -> None:
        result = result or PublishResult(success=False, platform="blogger", error="not_published")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO posts
                (source_url, title, slug, meta_description, labels, html, platform, platform_post_id,
                 platform_url, status, error, created_at, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    post.source_url,
                    post.title,
                    post.slug,
                    post.meta_description,
                    ",".join(post.labels),
                    post.html,
                    result.platform,
                    result.post_id,
                    result.url,
                    "published" if result.success else post.status,
                    result.error,
                    post.generated_at.isoformat(),
                    datetime.now(timezone.utc).isoformat() if result.success else None,
                ),
            )

    def recent_posts(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM posts ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            articles = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
            posts = conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"]
            published = conn.execute("SELECT COUNT(*) AS c FROM posts WHERE status = 'published'").fetchone()["c"]
            drafts = conn.execute("SELECT COUNT(*) AS c FROM posts WHERE status = 'draft'").fetchone()["c"]
        return {"articles": articles, "posts": posts, "published": published, "drafts": drafts}
