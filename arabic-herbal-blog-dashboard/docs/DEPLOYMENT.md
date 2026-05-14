# Deployment guide

## Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## PythonAnywhere

1. Upload the project.
2. Create a virtualenv and install requirements.
3. Add environment variables or upload `.env` privately.
4. Use a scheduled task:

```bash
cd /home/YOURUSER/arabic-herbal-blog-dashboard && /home/YOURUSER/.virtualenvs/blog/bin/python main.py run-once --limit 2
```

## Docker

```bash
docker build -t arabic-herbal-blog-dashboard .
docker run --env-file .env -p 8501:8501 arabic-herbal-blog-dashboard
```

## VPS with systemd scheduler

Use cron for the worker:

```cron
0 */4 * * * cd /opt/arabic-herbal-blog-dashboard && /opt/arabic-herbal-blog-dashboard/.venv/bin/python main.py run-once --limit 2 >> logs/cron.log 2>&1
```

## Safety recommendation

For health content, run in draft mode and review posts in Blogger before publishing live.
