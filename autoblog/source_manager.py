from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import DATA_DIR, SOURCES_FILE_JSON, SOURCES_FILE_YAML, get_settings, load_sources


def get_source_file() -> Path:
    if SOURCES_FILE_YAML.exists():
        return SOURCES_FILE_YAML
    return SOURCES_FILE_JSON


def _normalize_source_config(raw: dict[str, Any]) -> dict[str, Any]:
    raw = raw or {}
    if "sources" not in raw and "rss_feeds" in raw:
        raw = {
            "default": raw.get("default", {}),
            "sources": [
                {
                    "id": feed.get("name", feed.get("url", "")).lower().replace(" ", "_")[:40],
                    "name": feed.get("name", feed.get("url", "")),
                    "type": "rss",
                    "enabled": feed.get("enabled", True),
                    "url": feed.get("url", ""),
                }
                for feed in raw.get("rss_feeds", [])
            ],
            "keywords": raw.get("keywords", []),
            "blocked_keywords": raw.get("blocked_keywords", []),
        }
    return raw


def get_active_sources(source_type: str | None = None) -> list[dict[str, Any]]:
    config = _normalize_source_config(load_sources())
    sources = config.get("sources", []) or []
    active = [source for source in sources if source.get("enabled", True)]
    if source_type:
        active = [source for source in active if source.get("type") == source_type]
    return active


def get_default_fetch_parameters() -> dict[str, str]:
    config = _normalize_source_config(load_sources())
    default = config.get("default", {}) or {}
    return {
        "language": default.get("language", "ar"),
        "country": default.get("country", ""),
        "category": default.get("category", "health"),
        "deep_search_minimum": default.get("deep_search_minimum", 5),
        "searx_instance": default.get("searx_instance", "https://searx.be"),
    }


def get_keywords() -> list[str]:
    config = _normalize_source_config(load_sources())
    return config.get("keywords", []) or []


def get_blocked_keywords() -> list[str]:
    config = _normalize_source_config(load_sources())
    return config.get("blocked_keywords", []) or []


def get_source_api_key(source: dict[str, Any]) -> str:
    explicit = source.get("api_key", "")
    if explicit:
        return str(explicit).strip()
    env_name = source.get("api_key_env") or source.get("apiKeyEnv") or source.get("api_key_env_name")
    if env_name:
        return os.getenv(str(env_name).strip(), "").strip()
    return ""


def normalize_source(source: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "id": source.get("id") or source.get("name", "unknown").lower().replace(" ", "_")[:40],
        "name": source.get("name", "Unnamed Source"),
        "type": source.get("type", "rss"),
        "enabled": bool(source.get("enabled", True)),
        "url": source.get("url", ""),
        "api_key": source.get("api_key", ""),
        "api_key_env": source.get("api_key_env", ""),
        "language": source.get("language", ""),
        "country": source.get("country", ""),
        "category": source.get("category", ""),
        "limit": int(source.get("limit", 10) or 10),
        "instance_url": source.get("instance_url", ""),
        "query_template": source.get("query_template", "{keyword} health news"),
    }
    if not normalized["api_key_env"] and normalized["type"] == "currents_api":
        normalized["api_key_env"] = "CURRENTS_API_KEY"
    return normalized


def save_sources(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SOURCES_FILE_YAML.exists() or SOURCES_FILE_YAML.suffix == ".yaml":
        with open(SOURCES_FILE_YAML, "w", encoding="utf-8") as handle:
            import yaml

            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
    else:
        with open(SOURCES_FILE_JSON, "w", encoding="utf-8") as handle:
            import json

            json.dump(data, handle, ensure_ascii=False, indent=2)
