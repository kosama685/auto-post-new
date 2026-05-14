from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import get_settings
from .logger_setup import logger
from .pipeline import BlogPipeline


def run_scheduled_job() -> None:
    settings = get_settings()
    pipeline = BlogPipeline()
    result = pipeline.run_once(limit=settings.max_posts_per_run, publish=True, as_draft=settings.blogger_post_as_draft)
    logger.info("Scheduled job result: %s", result)


def start_scheduler() -> None:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(
        run_scheduled_job,
        "interval",
        hours=max(settings.post_interval_hours, 1),
        id="arabic_health_blog_job",
        replace_existing=True,
    )
    logger.info("Scheduler started. Interval: every %s hours", settings.post_interval_hours)
    run_scheduled_job()
    scheduler.start()
