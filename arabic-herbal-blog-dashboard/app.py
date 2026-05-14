from __future__ import annotations

import json
import logging
import sys
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

# Set page config FIRST, before any other Streamlit commands
st.set_page_config(
    page_title="Arabic Herbal Blog Dashboard",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Suppress verbose Streamlit logging
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
.stTabs {min-height: 500px;}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🌿 Arabic Herbal Health Blog Dashboard")
st.caption("Fetch Arabic health content, rewrite safely, optimize SEO, and publish to Blogger.")

# Initialize session state
if "app_ready" not in st.session_state:
    st.session_state.app_ready = False
    st.session_state.settings = None
    st.session_state.storage = None
    st.session_state.error = None

# Try to load all modules with comprehensive error handling
try:
    from autoblog.config import ENV_FILE, get_settings, load_sources, save_sources, write_env
    from autoblog.fetcher import fetch_articles
    from autoblog.pipeline import BlogPipeline
    from autoblog.publisher_blogger import authorize_blogger
    from autoblog.storage import Storage
    
    if not st.session_state.app_ready:
        try:
            st.session_state.settings = get_settings()
            st.session_state.storage = Storage()
            st.session_state.app_ready = True
        except Exception as init_err:
            st.session_state.error = f"Initialization error: {str(init_err)}"
            st.session_state.app_ready = False
except ImportError as import_err:
    st.error(f"❌ Module import failed: {str(import_err)}")
    st.info("Make sure all dependencies are installed: `pip install -r requirements.txt`")
    sys.exit(1)
except Exception as e:
    st.error(f"❌ Unexpected error: {str(e)}")
    st.text(traceback.format_exc())
    sys.exit(1)

# Display initialization errors if any
if st.session_state.error:
    st.warning(f"⚠️ {st.session_state.error}")

# Only proceed if app is ready
if not st.session_state.app_ready:
    st.info("🔄 App initializing... Please refresh the page.")
    st.stop()

settings = st.session_state.settings
storage = st.session_state.storage

# Display dashboard stats safely
try:
    stats = storage.stats()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fetched articles", stats.get("articles", 0))
    col2.metric("Saved posts", stats.get("posts", 0))
    col3.metric("Published", stats.get("published", 0))
    col4.metric("Draft/previews", stats.get("drafts", 0))
except Exception as e:
    st.warning(f"Could not load stats: {str(e)}")

try:
    with st.sidebar:
        st.header("Target website")
        st.success("Posting target: Blogger / Blogspot")
        st.write("Set `BLOGGER_BLOG_ID` and authorize Google OAuth before publishing.")
        st.divider()
        st.header("Actions")
        if st.button("Authorize Blogger OAuth"):
            try:
                authorize_blogger()
                st.success("Blogger OAuth completed and token saved.")
            except Exception as exc:
                st.error(str(exc))

    tabs = st.tabs(["Settings", "Sources", "Fetch & Preview", "Generate & Publish", "History", "Logs"])

    with tabs[0]:
        st.subheader("API keys and publishing settings")
        with st.form("settings_form"):
            openai_key = st.text_input("OPENAI_API_KEY", value=settings.openai_api_key, type="password")
            openai_model = st.text_input("OPENAI_MODEL", value=settings.openai_model)
            newsapi_key = st.text_input("NEWSAPI_KEY optional", value=settings.newsapi_key, type="password")
            blogger_blog_id = st.text_input("BLOGGER_BLOG_ID", value=settings.blogger_blog_id)
            google_client_secret_file = st.text_input("GOOGLE_CLIENT_SECRET_FILE", value=settings.google_client_secret_file)
            google_token_file = st.text_input("GOOGLE_TOKEN_FILE", value=settings.google_token_file)
            site_name = st.text_input("SITE_NAME", value=settings.site_name)
            post_as_draft = st.checkbox("Publish to Blogger as draft", value=settings.blogger_post_as_draft)
            enable_ai_rewrite = st.checkbox("Enable AI rewrite", value=settings.enable_ai_rewrite)
            enable_image_generation = st.checkbox("Enable image generation", value=settings.enable_image_generation)
            interval = st.number_input("POST_INTERVAL_HOURS", min_value=1, max_value=168, value=settings.post_interval_hours)
            max_posts = st.number_input("MAX_POSTS_PER_RUN", min_value=1, max_value=20, value=settings.max_posts_per_run)
            disclaimer = st.text_area("MEDICAL_DISCLAIMER", value=settings.medical_disclaimer)
            submitted = st.form_submit_button("Save settings to .env")
            if submitted:
                write_env(
                    {
                        "OPENAI_API_KEY": openai_key,
                        "OPENAI_MODEL": openai_model,
                        "NEWSAPI_KEY": newsapi_key,
                        "BLOGGER_BLOG_ID": blogger_blog_id,
                        "GOOGLE_CLIENT_SECRET_FILE": google_client_secret_file,
                        "GOOGLE_TOKEN_FILE": google_token_file,
                        "SITE_NAME": site_name,
                        "BLOGGER_POST_AS_DRAFT": str(post_as_draft).lower(),
                        "ENABLE_AI_REWRITE": str(enable_ai_rewrite).lower(),
                        "ENABLE_IMAGE_GENERATION": str(enable_image_generation).lower(),
                        "POST_INTERVAL_HOURS": str(interval),
                        "MAX_POSTS_PER_RUN": str(max_posts),
                        "MEDICAL_DISCLAIMER": disclaimer,
                        "TARGET_PLATFORM": "blogger",
                    }
                )
                st.success(f"Saved settings to {ENV_FILE}")

    with tabs[1]:
        st.subheader("Source websites and keywords")
        sources = load_sources()
        feeds = sources.get("rss_feeds", [])
        keywords = sources.get("keywords", [])
        blocked = sources.get("blocked_keywords", [])

        st.write("These are the websites the system starts fetching from. Posting goes to Blogger.")
        feeds_df = pd.DataFrame(feeds or [{"name": "", "url": "", "enabled": True}])
        edited = st.data_editor(feeds_df, num_rows="dynamic", use_container_width=True)
        keywords_text = st.text_area("Arabic target keywords, one per line", value="\n".join(keywords), height=140)
        blocked_text = st.text_area("Blocked unsafe claim words, one per line", value="\n".join(blocked), height=100)
        if st.button("Save sources"):
            rows = edited.fillna("").to_dict(orient="records")
            cleaned = []
            for row in rows:
                url = str(row.get("url", "")).strip()
                if not url:
                    continue
                cleaned.append(
                    {
                        "name": str(row.get("name", "")).strip() or url,
                        "url": url,
                        "enabled": bool(row.get("enabled", True)),
                    }
                )
            save_sources(
                {
                    "rss_feeds": cleaned,
                    "keywords": [x.strip() for x in keywords_text.splitlines() if x.strip()],
                    "blocked_keywords": [x.strip() for x in blocked_text.splitlines() if x.strip()],
                }
            )
            st.success("Saved source websites and keywords.")

    with tabs[2]:
        st.subheader("Fetch and preview source articles")
        limit = st.slider("Limit per source", 1, 20, settings.fetch_limit_per_source)
        if st.button("Fetch latest articles"):
            with st.spinner("Fetching configured source websites..."):
                articles = fetch_articles(include_newsapi=True, limit_per_source=limit)
            st.session_state["articles"] = articles
            st.success(f"Fetched {len(articles)} articles.")

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
            selected_idx = st.selectbox("Select article to inspect", list(range(len(articles))), format_func=lambda i: articles[i].title)
            selected = articles[selected_idx]
            st.markdown(f"<div class='rtl'><h3>{selected.title}</h3><p>{selected.summary}</p></div>", unsafe_allow_html=True)
            st.link_button("Open source", selected.source_url)

    with tabs[3]:
        st.subheader("Generate SEO post and publish")
        pipeline = BlogPipeline()
        articles = st.session_state.get("articles", [])
        publish_mode = st.radio("Mode", ["Preview only", "Publish to Blogger draft", "Publish live to Blogger"], horizontal=True)

        if articles:
            selected_idx = st.selectbox("Article", list(range(len(articles))), format_func=lambda i: articles[i].title, key="publish_article")
            if st.button("Generate post"):
                with st.spinner("Generating rewritten Arabic SEO article..."):
                    try:
                        post = pipeline.generate_post(articles[selected_idx])
                        st.session_state["generated_post"] = post
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
                result = None
                if publish_mode == "Preview only":
                    from autoblog.models import PublishResult

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
        if st.button("Run once"):
            with st.spinner("Running pipeline..."):
                result = pipeline.run_once(limit=int(run_limit), publish=full_publish, as_draft=settings.blogger_post_as_draft)
            st.json(result)

    with tabs[4]:
        st.subheader("Recent generated/published posts")
        rows = storage.recent_posts(50)
        if rows:
            df = pd.DataFrame([dict(r) for r in rows])
            st.dataframe(df[["id", "title", "status", "platform", "platform_url", "created_at", "error"]], use_container_width=True)
        else:
            st.info("No posts yet.")

    with tabs[5]:
        st.subheader("Logs")
        log_path = Path("logs/autoblog.log")
        if log_path.exists():
            st.code("\n".join(log_path.read_text(encoding="utf-8").splitlines()[-300:]), language="text")
        else:
            st.info("No log file yet.")

except Exception as e:
    st.error(f"❌ Dashboard error: {str(e)}")
    st.text(traceback.format_exc())
