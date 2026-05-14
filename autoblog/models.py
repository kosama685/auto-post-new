from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(slots=True)
class SourceArticle:
    title: str
    summary: str
    source_url: str
    source_name: str = "Unknown"
    author: str = "Unknown"
    published_at: Optional[datetime] = None
    content: str = ""
    image_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def body_text(self) -> str:
        return (self.content or self.summary or "").strip()

    def normalized_publish_date(self) -> str:
        dt = self.published_at or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


@dataclass(slots=True)
class GeneratedPost:
    title: str
    html: str
    meta_description: str
    labels: list[str]
    source_url: str
    source_name: str
    slug: str
    image_url: str = ""
    status: str = "draft"
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class PublishResult:
    success: bool
    platform: str
    post_id: str = ""
    url: str = ""
    error: str = ""
    response: dict[str, Any] = field(default_factory=dict)
