from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup


def clean_text(value: str) -> str:
    soup = BeautifulSoup(value or "", "lxml")
    text = soup.get_text(" ")
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def html_escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def source_hash(source_url: str, title: str = "") -> str:
    base = (source_url or title).strip().lower()
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def parse_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def make_slug(text: str, max_len: int = 80) -> str:
    text = clean_text(text).lower()
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ى": "ي",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^\w\s\-\u0600-\u06FF]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:max_len].strip("-") or "arabic-health-post"


def domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.replace("www.", "")
        return netloc or "source"
    except Exception:
        return "source"


def truncate_words(text: str, max_chars: int = 150) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def contains_blocked_claims(text: str, blocked_keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in blocked_keywords)
