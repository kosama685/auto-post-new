from __future__ import annotations

import argparse
import json

from autoblog.config import get_settings
from autoblog.storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Arabic Herbal Health Blog automation")
    sub = parser.add_subparsers(dest="command", required=True)

    run_once = sub.add_parser("run-once", help="Fetch, rewrite, and optionally publish posts once")
    run_once.add_argument("--limit", type=int, default=None)
    run_once.add_argument("--no-publish", action="store_true", help="Generate previews without publishing")
    run_once.add_argument("--live", action="store_true", help="Publish live instead of draft")

    sub.add_parser("schedule", help="Run the scheduled posting worker")
    sub.add_parser("authorize-blogger", help="Run Google OAuth flow for Blogger")
    sub.add_parser("stats", help="Show local database stats")

    args = parser.parse_args()
    settings = get_settings()

    if args.command == "authorize-blogger":
        from autoblog.publisher_blogger import authorize_blogger

        creds = authorize_blogger()
        print("Blogger OAuth completed. Token saved.")
        print(f"Scopes: {creds.scopes}")
    elif args.command == "schedule":
        from autoblog.scheduler import start_scheduler

        start_scheduler()
    elif args.command == "stats":
        print(json.dumps(Storage().stats(), ensure_ascii=False, indent=2))
    elif args.command == "run-once":
        from autoblog.pipeline import BlogPipeline

        pipeline = BlogPipeline()
        result = pipeline.run_once(
            limit=args.limit or settings.max_posts_per_run,
            publish=not args.no_publish,
            as_draft=not args.live,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
