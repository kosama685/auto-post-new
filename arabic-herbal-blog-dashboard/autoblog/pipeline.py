from __future__ import annotations

from dataclasses import asdict

from .config import get_settings, load_sources
from .fetcher import fetch_articles
from .image_gen import get_featured_image_url
from .logger_setup import logger
from .models import GeneratedPost, PublishResult, SourceArticle
from .publisher_blogger import BloggerPublisher
from .rewriter import Rewriter
from .seo_optimizer import finalize_post, has_minimum_quality
from .storage import Storage
from .utils import contains_blocked_claims


class BlogPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = Storage()
        self.rewriter = Rewriter()

    def fetch_new_articles(self, limit_per_source: int | None = None) -> list[SourceArticle]:
        all_articles = fetch_articles(include_newsapi=True, limit_per_source=limit_per_source)
        sources = load_sources()
        blocked = sources.get("blocked_keywords", [])
        new_articles: list[SourceArticle] = []
        for article in all_articles:
            if contains_blocked_claims(article.title + " " + article.body_text, blocked):
                logger.warning("Skipping unsafe/blocked article: %s", article.title)
                continue
            if self.storage.article_exists(article):
                continue
            self.storage.save_article(article)
            new_articles.append(article)
        logger.info("Fetched %s new articles", len(new_articles))
        return new_articles

    def generate_post(self, article: SourceArticle) -> GeneratedPost:
        html = self.rewriter.rewrite(article)
        image_url = get_featured_image_url(article.title, article.image_url)
        post = finalize_post(article, html, image_url=image_url)
        ok, reason = has_minimum_quality(post.html)
        if not ok:
            raise ValueError(reason)
        return post

    def publish_post(self, post: GeneratedPost, as_draft: bool | None = None) -> PublishResult:
        if self.settings.target_platform.lower() != "blogger":
            return PublishResult(success=False, platform=self.settings.target_platform, error="Only Blogger is implemented")
        publisher = BloggerPublisher()
        return publisher.publish(post, as_draft=as_draft)

    def run_once(self, limit: int | None = None, publish: bool = True, as_draft: bool | None = None) -> dict:
        limit = limit or self.settings.max_posts_per_run
        articles = self.fetch_new_articles(limit_per_source=self.settings.fetch_limit_per_source)
        selected = articles[:limit]
        generated: list[GeneratedPost] = []
        results: list[PublishResult] = []

        for article in selected:
            try:
                post = self.generate_post(article)
                generated.append(post)
                result = PublishResult(success=False, platform="blogger", error="preview_only")
                if publish:
                    result = self.publish_post(post, as_draft=as_draft)
                self.storage.save_post(post, result)
                results.append(result)
            except Exception as exc:
                logger.exception("Failed processing article %s: %s", article.source_url, exc)
                results.append(PublishResult(success=False, platform="blogger", error=str(exc)))

        return {
            "fetched": len(articles),
            "selected": len(selected),
            "generated": len(generated),
            "published": sum(1 for r in results if r.success),
            "results": [asdict(r) for r in results],
        }
