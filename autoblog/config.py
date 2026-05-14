from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
GENERATED_IMAGE_DIR = DATA_DIR / "generated_images"
SOURCES_FILE_JSON = DATA_DIR / "sources.json"
SOURCES_FILE_YAML = DATA_DIR / "sources.yaml"
ENV_FILE = ROOT_DIR / ".env"

for directory in (DATA_DIR, LOG_DIR, GENERATED_IMAGE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

load_dotenv(ENV_FILE)


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw is not None and raw != "" else default
    except ValueError:
        return default


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    app_name: str = _str("APP_NAME", "Arabic Herbal Health Blog Dashboard")
    app_env: str = _str("APP_ENV", "local")
    timezone: str = _str("TZ", "Asia/Riyadh")

    openai_api_key: str = _str("OPENAI_API_KEY")
    openai_model: str = _str("OPENAI_MODEL", "gpt-4o-mini")
    openai_image_model: str = _str("OPENAI_IMAGE_MODEL", "gpt-image-1")
    enable_ai_rewrite: bool = _bool("ENABLE_AI_REWRITE", True)
    enable_image_generation: bool = _bool("ENABLE_IMAGE_GENERATION", False)

    newsapi_key: str = _str("NEWSAPI_KEY")
    newsapi_language: str = _str("NEWSAPI_LANGUAGE", "ar")
    newsapi_country: str = _str("NEWSAPI_COUNTRY", "")
    newsapi_category: str = _str("NEWSAPI_CATEGORY", "health")
    newsapi_page_size: int = _int("NEWSAPI_PAGE_SIZE", 10)

    currents_api_key: str = _str("CURRENTS_API_KEY")
    currents_api_language: str = _str("CURRENTS_API_LANGUAGE", "ar")
    currents_api_country: str = _str("CURRENTS_API_COUNTRY", "")
    currents_api_category: str = _str("CURRENTS_API_CATEGORY", "health")

    post_interval_hours: int = _int("POST_INTERVAL_HOURS", 4)
    max_posts_per_run: int = _int("MAX_POSTS_PER_RUN", 2)
    fetch_limit_per_source: int = _int("FETCH_LIMIT_PER_SOURCE", 10)
    history_ttl_days: int = _int("HISTORY_TTL_DAYS", 7)
    request_delay_seconds: int = _int("REQUEST_DELAY_SECONDS", 2)

    target_platform: str = _str("TARGET_PLATFORM", "blogger")
    blogger_blog_id: str = _str("BLOGGER_BLOG_ID")
    blogger_post_as_draft: bool = _bool("BLOGGER_POST_AS_DRAFT", True)
    google_client_secret_file: str = _str("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")
    google_token_file: str = _str("GOOGLE_TOKEN_FILE", "token.json")

    cloudinary_cloud_name: str = _str("CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = _str("CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = _str("CLOUDINARY_API_SECRET")

    post_interval_hours: int = _int("POST_INTERVAL_HOURS", 4)
    max_posts_per_run: int = _int("MAX_POSTS_PER_RUN", 2)
    fetch_limit_per_source: int = _int("FETCH_LIMIT_PER_SOURCE", 10)
    request_delay_seconds: int = _int("REQUEST_DELAY_SECONDS", 2)

    site_name: str = _str("SITE_NAME", "مدونة الصحة والأعشاب")
    site_base_url: str = _str("SITE_BASE_URL")
    default_author: str = _str("DEFAULT_AUTHOR", "فريق التحرير")
    saudi_geo_targeting: bool = _bool("SAUDI_GEO_TARGETING", True)
    require_review_before_publish: bool = _bool("REQUIRE_REVIEW_BEFORE_PUBLISH", True)
    medical_disclaimer: str = _str(
        "MEDICAL_DISCLAIMER",
        "المعلومات الواردة في هذا المقال عامة ولا تغني عن استشارة الطبيب أو الصيدلي المختص.",
    )

    database_url: str = _str("DATABASE_URL", "sqlite:///data/app.db")
    log_level: str = _str("LOG_LEVEL", "INFO")

    @property
    def db_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            rel = self.database_url.replace("sqlite:///", "", 1)
            path = Path(rel)
            return path if path.is_absolute() else ROOT_DIR / path
        return ROOT_DIR / "data" / "app.db"

    @property
    def google_client_secret_path(self) -> Path:
        path = Path(self.google_client_secret_file)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def google_token_path(self) -> Path:
        path = Path(self.google_token_file)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def has_cloudinary(self) -> bool:
        return all([self.cloudinary_cloud_name, self.cloudinary_api_key, self.cloudinary_api_secret])


def get_settings() -> Settings:
    load_dotenv(ENV_FILE, override=True)
    return Settings()


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sources() -> dict[str, Any]:
    if SOURCES_FILE_YAML.exists():
        return _read_yaml(SOURCES_FILE_YAML)
    if SOURCES_FILE_JSON.exists():
        return _read_json(SOURCES_FILE_JSON)
    return {"default": {}, "sources": [], "keywords": [], "blocked_keywords": []}


def save_sources(data: dict[str, Any]) -> None:
    if SOURCES_FILE_YAML.exists() or yaml:
        _write_yaml(SOURCES_FILE_YAML, data)
    else:
        _write_json(SOURCES_FILE_JSON, data)


def write_env(updates: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            existing[key.strip()] = value.strip().strip('"').strip("'")
    existing.update({k: str(v) for k, v in updates.items()})
    lines = [f'{key}="{value}"' for key, value in sorted(existing.items())]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
