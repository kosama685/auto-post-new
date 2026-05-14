# Arabic Herbal Health Blog Dashboard

A complete Python project for fetching Arabic health/herbal content from configured RSS feeds and NewsAPI, rewriting it safely into unique Arabic HTML, optimizing it for SEO, and publishing it to Blogger.

> Medical safety: every generated post includes a general-information disclaimer and avoids diagnosis/treatment guarantees. Review posts before publishing, especially health content.

## What website does it post to?

The default publishing target is **Blogger / Blogspot** through the Blogger API v3. You can publish as a draft first, review inside Blogger, then publish manually.

Default source websites/feeds are configurable in the dashboard and in `data/sources.json`:

- WebTeb Health RSS
- Al Jazeera Health RSS
- Al-Madina Health RSS

You may add or remove feeds from the dashboard.

## Project structure

```text
arabic-herbal-blog-dashboard/
├── app.py                       # Streamlit dashboard
├── main.py                      # CLI entry point
├── .env.example                 # Copy to .env and fill your keys
├── requirements.txt
├── Dockerfile
├── data/
│   ├── sources.json             # RSS feeds and keywords
│   └── app.db                   # Created at runtime
├── logs/                        # Runtime logs
├── docs/
│   ├── BLOGGER_OAUTH.md
│   └── DEPLOYMENT.md
├── scripts/
│   ├── run_dashboard.sh
│   └── run_once.sh
└── autoblog/
    ├── config.py
    ├── fetcher.py
    ├── image_gen.py
    ├── logger_setup.py
    ├── models.py
    ├── pipeline.py
    ├── publisher_blogger.py
    ├── rewriter.py
    ├── scheduler.py
    ├── seo_optimizer.py
    ├── storage.py
    └── utils.py
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

Open the dashboard, enter your API keys, Blogger blog ID, keywords, source RSS feeds, and publishing mode.

## Required keys

### OpenAI
Used to rewrite articles in Arabic and optionally generate images.

- `OPENAI_API_KEY`
- `OPENAI_MODEL` default: `gpt-4o-mini`

### Blogger
Used to publish posts to a Blogger blog.

- `BLOGGER_BLOG_ID`
- `GOOGLE_CLIENT_SECRET_FILE` path to your downloaded OAuth client JSON file
- `GOOGLE_TOKEN_FILE` path where the OAuth token will be stored, usually `token.json`

Run this once to authorize Blogger:

```bash
python main.py authorize-blogger
```

### NewsAPI optional
RSS feeds work without NewsAPI. NewsAPI adds more discovery.

- `NEWSAPI_KEY`

### Cloudinary optional
Used to host generated images if you want stable image URLs inside Blogger posts.

- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

If Cloudinary is not configured, the system skips image upload and publishes text-only posts or uses remote image URLs when available.

## Run once

```bash
python main.py run-once --limit 3
```

## Run scheduler

```bash
python main.py schedule
```

The schedule interval is controlled by `POST_INTERVAL_HOURS` in `.env`.

## Dashboard

```bash
streamlit run app.py
```

Dashboard features:

- Set and save API keys locally in `.env`
- Add/remove RSS source URLs
- Add Arabic target keywords
- Preview fetched articles
- Generate rewritten SEO post previews
- Publish to Blogger as draft or live post
- View logs and published history

## Posting workflow

1. Fetch recent articles from your RSS feeds and NewsAPI.
2. Store source URLs in SQLite to avoid duplicate posts.
3. Rewrite each article into original Arabic HTML using OpenAI.
4. Add H2/H3 headings, FAQ, schema markup, source attribution, and medical disclaimer.
5. Optionally generate and upload an image.
6. Publish to Blogger as draft by default.

## Compliance checklist

- Do not publish copied source text verbatim.
- Always include source attribution.
- Keep medical claims cautious and general.
- Do not replace professional medical advice.
- Review health content before publishing.
- Respect robots.txt and source terms.

## Environment settings

See `.env.example` for all available settings.
