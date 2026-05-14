from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
                CREATE TABLE IF NOT EXISTS fetch_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_at TEXT NOT NULL,
                    source_id TEXT,
                    source_name TEXT,
                    source_type TEXT,
                    source_url TEXT,
                    success INTEGER NOT NULL,
                    item_count INTEGER NOT NULL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
                CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
                CREATE INDEX IF NOT EXISTS idx_fetch_runs_source ON fetch_runs(source_id, source_type);
                """
            )

    def article_seen_recently(self, article: SourceArticle, ttl_days: int | None = None) -> bool:
        ttl_days = ttl_days if ttl_days is not None else self.settings.history_ttl_days
        threshold = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        h = source_hash(article.source_url, article.title)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM articles
                WHERE (source_hash = ? OR source_url = ?)
                  AND fetched_at >= ?
                LIMIT 1
                """,
                (h, article.source_url, threshold.isoformat()),
            ).fetchone()
            return row is not None

    def article_exists(self, article: SourceArticle, ttl_days: int | None = None) -> bool:
        return self.article_seen_recently(article, ttl_days=ttl_days)

    def log_fetch_run(
        self,
        source_id: str | None,
        source_name: str,
        source_type: str,
        source_url: str,
        success: bool,
        item_count: int,
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO fetch_runs
                (run_at, source_id, source_name, source_type, source_url, success, item_count, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    source_id,
                    source_name,
                    source_type,
                    source_url,
                    1 if success else 0,
                    item_count,
                    error,
                ),
            )

    def save_article(self, article: SourceArticle, status: str = "fetched") -> None:
        h = source_hash(article.source_url, article.title)
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO articles
                (id, title, source_url, source_hash, source_name, author, published_at, fetched_at, status)
                VALUES (
                    COALESCE(
                        (SELECT id FROM articles WHERE source_url = ? OR source_hash = ? LIMIT 1),
                        NULL
                    ),
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    article.source_url,
                    h,
                    article.title,
                    article.source_url,
                    h,
                    article.source_name,
                    article.author,
                    article.normalized_publish_date(),
                    fetched_at,
                    status,
                ),
            )

    def clear_history(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM articles")

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

    def recent_fetch_runs(self, limit: int = 50) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM fetch_runs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )

    def fetch_summary(self) -> dict[str, int]:
        with self.connect() as conn:
            total_runs = conn.execute("SELECT COUNT(*) AS c FROM fetch_runs").fetchone()["c"]
            successful = conn.execute("SELECT COUNT(*) AS c FROM fetch_runs WHERE success=1").fetchone()["c"]
            failed = conn.execute("SELECT COUNT(*) AS c FROM fetch_runs WHERE success=0").fetchone()["c"]
            sources = conn.execute("SELECT COUNT(DISTINCT source_id) AS c FROM fetch_runs").fetchone()["c"]
        return {"fetch_runs": total_runs, "success": successful, "failed": failed, "sources": sources}

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            articles = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
            posts = conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"]
            published = conn.execute("SELECT COUNT(*) AS c FROM posts WHERE status = 'published'").fetchone()["c"]
            drafts = conn.execute("SELECT COUNT(*) AS c FROM posts WHERE status = 'draft'").fetchone()["c"]
        return {"articles": articles, "posts": posts, "published": published, "drafts": drafts}
