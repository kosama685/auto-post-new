from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .config import get_settings, load_sources
from .models import GeneratedPost, SourceArticle
from .utils import clean_text, domain_from_url, html_escape, make_slug, truncate_words


def build_meta_description(title: str, body: str, keyword: str = "") -> str:
    base = clean_text(body)
    if keyword and keyword not in base:
        base = f"{keyword}: {base}"
    meta = truncate_words(base or title, 150)
    return meta[:160]


def sanitize_html(value: str) -> str:
    allowed_tags = {
        "p", "br", "strong", "em", "ul", "ol", "li", "h1", "h2", "h3", "h4",
        "blockquote", "a", "img", "div", "section", "article", "span"
    }
    allowed_attrs = {
        "a": {"href", "target", "rel"},
        "img": {"src", "alt", "loading", "width", "height"},
        "div": {"dir", "class"},
        "article": {"dir", "class"},
        "section": {"class"},
    }
    soup = BeautifulSoup(value or "", "lxml")
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
            continue
        attrs = dict(tag.attrs)
        for attr in attrs:
            if attr not in allowed_attrs.get(tag.name, set()):
                del tag.attrs[attr]
        if tag.name == "a":
            tag.attrs.setdefault("target", "_blank")
            tag.attrs.setdefault("rel", "nofollow noopener noreferrer")
    body = soup.body.decode_contents() if soup.body else str(soup)
    return body.strip()


def build_schema(post: GeneratedPost, article: SourceArticle) -> str:
    settings = get_settings()
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post.title,
        "description": post.meta_description,
        "inLanguage": "ar",
        "author": {"@type": "Organization", "name": settings.default_author},
        "publisher": {"@type": "Organization", "name": settings.site_name},
        "datePublished": article.normalized_publish_date(),
        "dateModified": datetime.now(timezone.utc).isoformat(),
        "mainEntityOfPage": post.source_url,
        "about": ["الصحة", "الأعشاب", "العناية الطبيعية"],
    }
    if post.image_url:
        schema["image"] = [post.image_url]
    return f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>'


def add_rtl_wrapper(html: str) -> str:
    return f'<article dir="rtl" class="arabic-health-post">\n{html}\n</article>'


def ensure_disclaimer(html: str) -> str:
    settings = get_settings()
    disclaimer = html_escape(settings.medical_disclaimer)
    if disclaimer in html:
        return html
    return f"{html}\n<hr><p><strong>تنبيه طبي:</strong> {disclaimer}</p>"


def add_source_attribution(html: str, article: SourceArticle) -> str:
    source = html_escape(article.source_name or domain_from_url(article.source_url))
    url = html_escape(article.source_url)
    attribution = (
        f'<p><small>المصدر الأصلي للمعلومة: '
        f'<a href="{url}" target="_blank" rel="nofollow noopener noreferrer">{source}</a>. '
        f'تمت إعادة الصياغة والتحرير مع مراعاة الدقة والسلامة.</small></p>'
    )
    return f"{html}\n{attribution}"


def add_image(html: str, image_url: str, alt: str) -> str:
    if not image_url:
        return html
    safe_url = html_escape(image_url)
    safe_alt = html_escape(alt)
    image_html = f'<p><img src="{safe_url}" alt="{safe_alt}" loading="lazy"></p>'
    return image_html + "\n" + html


def choose_labels(title: str, body: str) -> list[str]:
    sources = load_sources()
    keywords = sources.get("keywords", [])[:5]
    labels = [kw for kw in keywords if kw in title or kw in body]
    if "الصحة" not in labels:
        labels.append("الصحة")
    if "الأعشاب" not in labels and any(token in title + body for token in ["عشب", "أعشاب", "طبيعي"]):
        labels.append("الأعشاب")
    return labels[:10]


def keyword_rich_title(article: SourceArticle) -> str:
    title = clean_text(article.title)
    if "الأعشاب" not in title and "صحة" not in title:
        return f"الصحة والأعشاب: {title}"
    return title


def finalize_post(article: SourceArticle, rewritten_html: str, image_url: str = "") -> GeneratedPost:
    title = keyword_rich_title(article)
    cleaned = sanitize_html(rewritten_html)
    cleaned = add_image(cleaned, image_url or article.image_url, title)
    cleaned = add_source_attribution(cleaned, article)
    cleaned = ensure_disclaimer(cleaned)
    labels = choose_labels(title, cleaned)
    meta = build_meta_description(title, cleaned, labels[0] if labels else "الصحة")
    slug = make_slug(title)
    post = GeneratedPost(
        title=title,
        html="",
        meta_description=meta,
        labels=labels,
        source_url=article.source_url,
        source_name=article.source_name,
        slug=slug,
        image_url=image_url or article.image_url,
        status="draft",
    )
    schema = build_schema(post, article)
    post.html = add_rtl_wrapper(f"<h1>{html_escape(title)}</h1>\n{cleaned}\n{schema}")
    return post


def has_minimum_quality(html: str) -> tuple[bool, str]:
    text = clean_text(html)
    if len(text) < 450:
        return False, "Generated content is too short."
    if re.search(r"شفاء نهائي|علاج مضمون|معجزة", text):
        return False, "Generated content contains unsafe absolute medical claims."
    return True, "ok"
