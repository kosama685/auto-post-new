from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

from autoblog.config import ENV_FILE, get_settings, load_sources, save_sources, write_env
from autoblog.fetcher import fetch_articles
from autoblog.pipeline import BlogPipeline
from autoblog.publisher_blogger import authorize_blogger
from autoblog.source_manager import get_default_fetch_parameters
from autoblog.storage import Storage

# Set page config FIRST, before any other Streamlit commands
st.set_page_config(
    page_title="Arabic Herbal Blog Dashboard",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

logging.getLogger("streamlit").setLevel(logging.WARNING)
logging.getLogger("streamlit.runtime.scriptrunner").setLevel(logging.ERROR)

st.markdown(
    """
<style>
@font-face {
    font-display: swap;
}
html, body {
    overflow-x: hidden;
}
.main .block-container {max-width: 1200px;}
.metric-card {border:1px solid #ddd;border-radius:12px;padding:16px;background:#fff;}
.rtl {direction: rtl; text-align: right;}
""",
    unsafe_allow_html=True,
)

st.title("🌿 Arabic Herbal Health Blog Dashboard")
st.caption("Configure sources, fetch articles, and monitor fetch status from one dashboard.")

if "app_ready" not in st.session_state:
    st.session_state.app_ready = False
    st.session_state.settings = None
    st.session_state.storage = None
    st.session_state.error = None
    st.session_state.articles = []
    st.session_state.generated_post = None

try:
    if not st.session_state.app_ready:
        st.session_state.settings = get_settings()
        st.session_state.storage = Storage()
        st.session_state.app_ready = True
except Exception as init_err:
    st.session_state.error = str(init_err)

if st.session_state.error:
    st.error(f"❌ Initialization failed: {st.session_state.error}")
    st.stop()

settings = st.session_state.settings
storage = st.session_state.storage
fetch_defaults = get_default_fetch_parameters()

try:
    stats = storage.stats()
    fetch_summary = storage.fetch_summary()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Fetched articles", stats.get("articles", 0))
    col2.metric("Saved posts", stats.get("posts", 0))
    col3.metric("Published", stats.get("published", 0))
    col4.metric("Draft/previews", stats.get("drafts", 0))
    col5.metric("Fetch runs", fetch_summary.get("fetch_runs", 0))
except Exception as exc:
    st.warning(f"Could not load stats: {exc}")

source_option = st.sidebar.selectbox(
    "Source type",
    ["RSS feeds", "Currents API", "GNews API", "SearxNG", "Both"],
    index=4,
)
source_type = {
    "RSS feeds": "rss",
    "Currents API": "currents",
    "GNews API": "gnews",
    "SearxNG": "searxng",
    "Both": "both",
}[source_option]

language = st.sidebar.selectbox("Language", ["ar", "en"], index=0 if fetch_defaults["language"] == "ar" else 1)
country = st.sidebar.selectbox("Country", ["", "sa", "us", "eg", "ae"], index=0)
category = st.sidebar.selectbox(
    "Category",
    ["health", "general", "science", "technology", "business"],
    index=0,
)

history_ttl_days = st.sidebar.slider(
    "History TTL (days)",
    min_value=1,
    max_value=30,
    value=settings.history_ttl_days,
    help="Only skip articles that were already seen within this window.",
)

deep_search_minimum = st.sidebar.slider(
    "Deep search minimum articles",
    min_value=1,
    max_value=20,
    value=fetch_defaults.get("deep_search_minimum", 5),
    help="If main sources return fewer articles, fallback to deep search.",
)

if st.sidebar.button("Clear history"):
    storage.clear_history()
    st.sidebar.success("Cleared seen article history.")

st.sidebar.markdown("---")
if st.sidebar.button("Fetch Now"):
    with st.spinner("Fetching configured sources…"):
        articles = fetch_articles(
            source_type=source_type,
            language=language,
            country=country,
            category=category,
            limit_per_source=settings.fetch_limit_per_source,
            deep_search_minimum=deep_search_minimum,
        )
    st.session_state.articles = articles
    st.success(f"Fetched {len(articles)} unique articles.")

st.sidebar.markdown("---")
if source_type in {"currents", "both"} and not settings.currents_api_key:
    st.sidebar.warning("CURRENTS_API_KEY is not configured.")

tabs = st.tabs(["Settings", "Sources", "Fetch & Preview", "Generate & Publish", "History", "Logs"])

with tabs[0]:
    st.subheader("Settings")
    with st.form("settings_form"):
        openai_key = st.text_input("OPENAI_API_KEY", value=settings.openai_api_key, type="password")
        openai_model = st.text_input("OPENAI_MODEL", value=settings.openai_model)
        currents_api_key = st.text_input("CURRENTS_API_KEY", value=settings.currents_api_key, type="password")
        newsapi_key = st.text_input("NEWSAPI_KEY optional", value=settings.newsapi_key, type="password")
        blogger_blog_id = st.text_input("BLOGGER_BLOG_ID", value=settings.blogger_blog_id)
        google_client_secret_file = st.text_input("GOOGLE_CLIENT_SECRET_FILE", value=settings.google_client_secret_file)
        google_token_file = st.text_input("GOOGLE_TOKEN_FILE", value=settings.google_token_file)
        post_as_draft = st.checkbox("Publish to Blogger as draft", value=settings.blogger_post_as_draft)
        enable_ai_rewrite = st.checkbox("Enable AI rewrite", value=settings.enable_ai_rewrite)
        enable_image_generation = st.checkbox("Enable image generation", value=settings.enable_image_generation)
        interval = st.number_input("POST_INTERVAL_HOURS", min_value=1, max_value=168, value=settings.post_interval_hours)
        max_posts = st.number_input("MAX_POSTS_PER_RUN", min_value=1, max_value=20, value=settings.max_posts_per_run)
        history_ttl_days_setting = st.number_input("HISTORY_TTL_DAYS", min_value=1, max_value=30, value=settings.history_ttl_days)
        disclaimer = st.text_area("MEDICAL_DISCLAIMER", value=settings.medical_disclaimer)
        submitted = st.form_submit_button("Save settings")
        if submitted:
            write_env(
                {
                    "OPENAI_API_KEY": openai_key,
                    "OPENAI_MODEL": openai_model,
                    "NEWSAPI_KEY": newsapi_key,
                    "CURRENTS_API_KEY": currents_api_key,
                    "BLOGGER_BLOG_ID": blogger_blog_id,
                    "GOOGLE_CLIENT_SECRET_FILE": google_client_secret_file,
                    "GOOGLE_TOKEN_FILE": google_token_file,
                    "SITE_NAME": settings.site_name,
                    "BLOGGER_POST_AS_DRAFT": str(post_as_draft).lower(),
                    "ENABLE_AI_REWRITE": str(enable_ai_rewrite).lower(),
                    "ENABLE_IMAGE_GENERATION": str(enable_image_generation).lower(),
                    "POST_INTERVAL_HOURS": str(interval),
                    "MAX_POSTS_PER_RUN": str(max_posts),
                    "HISTORY_TTL_DAYS": str(history_ttl_days_setting),
                    "MEDICAL_DISCLAIMER": disclaimer,
                    "TARGET_PLATFORM": "blogger",
                }
            )
            st.success(f"Saved settings to {ENV_FILE}")

with tabs[1]:
    st.subheader("Sources")
    source_config = load_sources()
    sources = source_config.get("sources", []) or []
    rows = []
    for source in sources:
        rows.append(
            {
                "id": source.get("id", ""),
                "name": source.get("name", ""),
                "type": source.get("type", "rss"),
                "enabled": source.get("enabled", True),
                "url": source.get("url", ""),
                "api_key_env": source.get("api_key_env", ""),
                "language": source.get("language", ""),
                "country": source.get("country", ""),
                "category": source.get("category", ""),
                "limit": source.get("limit", 10),
                "instance_url": source.get("instance_url", ""),
                "query_template": source.get("query_template", "{keyword} health news"),
            }
        )

    st.write("Edit active sources and API keys here. Save to persist to `data/sources.yaml` or `data/sources.json`.")
    edited = st.data_editor(pd.DataFrame(rows), num_rows="dynamic", use_container_width=True)
    keywords_text = st.text_area(
        "Search keywords (one per line)",
        value="\n".join(source_config.get("keywords", [])),
        height=140,
    )
    blocked_text = st.text_area(
        "Blocked keywords (one per line)",
        value="\n".join(source_config.get("blocked_keywords", [])),
        height=100,
    )
    if st.button("Save sources"):
        cleaned = []
        for row in edited.fillna("").to_dict(orient="records"):
            if not row.get("name") and not row.get("url"):
                continue
            cleaned.append(
                {
                    "id": str(row.get("id") or row.get("name", "")).strip(),
                    "name": str(row.get("name", "")).strip(),
                    "type": str(row.get("type", "rss")).strip(),
                    "enabled": bool(row.get("enabled", True)),
                    "url": str(row.get("url", "")).strip(),
                    "api_key_env": str(row.get("api_key_env", "")).strip(),
                    "language": str(row.get("language", "")).strip(),
                    "country": str(row.get("country", "")).strip(),
                    "category": str(row.get("category", "")).strip(),
                    "limit": int(row.get("limit") or 10),
                    "instance_url": str(row.get("instance_url", "")).strip(),
                    "query_template": str(row.get("query_template", "{keyword} health news")).strip(),
                }
            )
        save_sources(
            {
                "default": source_config.get("default", {}),
                "sources": cleaned,
                "keywords": [x.strip() for x in keywords_text.splitlines() if x.strip()],
                "blocked_keywords": [x.strip() for x in blocked_text.splitlines() if x.strip()],
            }
        )
        st.success("Saved source configuration.")

with tabs[2]:
    st.subheader("Fetch & Preview")
    st.write("Use the sidebar fetch controls and press Fetch latest articles.")
    limit = st.slider("Limit per source", 1, 30, settings.fetch_limit_per_source)
    if st.button("Fetch latest articles"):
        with st.spinner("Fetching configured sources…"):
            articles = fetch_articles(
                source_type=source_type,
                language=language,
                country=country,
                category=category,
                limit_per_source=limit,
                deep_search_minimum=deep_search_minimum,
            )
        st.session_state.articles = articles
        st.success(f"Fetched {len(articles)} unique articles.")

    articles = st.session_state.get("articles", [])
    if articles:
        table = [
            {
                "title": a.title,
                "source": a.source_name,
                "url": a.source_url,
                "published": a.normalized_publish_date(),
            }
            for a in articles
        ]
        st.dataframe(pd.DataFrame(table), use_container_width=True)
        selected_idx = st.selectbox(
            "Select article to inspect",
            list(range(len(articles))),
            format_func=lambda i: articles[i].title,
        )
        selected = articles[selected_idx]
        st.markdown(f"<div class='rtl'><h3>{selected.title}</h3><p>{selected.summary}</p></div>", unsafe_allow_html=True)
        st.write(f"Source: {selected.source_name}")
        st.write(f"URL: {selected.source_url}")
    else:
        st.info("Press Fetch latest articles to load new content.")

with tabs[3]:
    st.subheader("Generate & Publish")
    pipeline = BlogPipeline()
    articles = st.session_state.get("articles", [])
    publish_mode = st.radio(
        "Mode",
        ["Preview only", "Publish to Blogger draft", "Publish live to Blogger"],
        horizontal=True,
    )

    if articles:
        selected_idx = st.selectbox(
            "Article",
            list(range(len(articles))),
            format_func=lambda i: articles[i].title,
            key="publish_article",
        )
        if st.button("Generate post"):
            with st.spinner("Generating rewritten Arabic SEO article…"):
                try:
                    post = pipeline.generate_post(articles[selected_idx])
                    st.session_state.generated_post = post
                    st.success("Generated post preview.")
                except Exception as exc:
                    st.error(str(exc))
    else:
        st.info("Fetch articles first from the Fetch & Preview tab.")

    post = st.session_state.get("generated_post")
    if post:
        st.write("Title:", post.title)
        st.write("Meta description:", post.meta_description)
        st.write("Labels:", ", ".join(post.labels))
        st.components.v1.html(post.html, height=600, scrolling=True)
        if st.button("Save / publish selected post"):
            from autoblog.models import PublishResult

            if publish_mode == "Preview only":
                result = PublishResult(success=False, platform="blogger", error="preview_only")
            else:
                as_draft = publish_mode == "Publish to Blogger draft"
                result = pipeline.publish_post(post, as_draft=as_draft)
            storage.save_post(post, result)
            if result.success:
                st.success(f"Published: {result.url or result.post_id}")
            else:
                st.warning(f"Saved locally. Publish result: {result.error}")

    st.divider()
    st.subheader("Run full pipeline")
    col_a, col_b = st.columns(2)
    run_limit = col_a.number_input("Posts this run", 1, 10, settings.max_posts_per_run)
    full_publish = col_b.checkbox("Publish during run", value=False)
    if st.button("Run pipeline once"):
        with st.spinner("Running pipeline…"):
            result = pipeline.run_once(
                limit=int(run_limit),
                publish=full_publish,
                as_draft=settings.blogger_post_as_draft,
                source_type=source_type,
                language=language,
                country=country,
                category=category,
                history_ttl_days=history_ttl_days,
            )
        st.json(result)

with tabs[4]:
    st.subheader("Recent activity")
    rows = storage.recent_posts(50)
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df[["id", "title", "status", "platform", "platform_url", "created_at", "error"]], use_container_width=True)
    else:
        st.info("No posts yet.")

    st.markdown("---")
    st.subheader("Fetch history")
    fetch_rows = storage.recent_fetch_runs(100)
    if fetch_rows:
        df = pd.DataFrame([dict(r) for r in fetch_rows])
        st.dataframe(df[["run_at", "source_type", "source_name", "source_url", "success", "item_count", "error"]], use_container_width=True)
    else:
        st.info("No fetch history yet.")

with tabs[5]:
    st.subheader("Logs")
    log_path = Path("logs/autoblog.log")
    if log_path.exists():
        st.code("\n".join(log_path.read_text(encoding="utf-8").splitlines()[-300:]), language="text")
    else:
        st.info("No log file yet.")
