from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import get_settings
from .logger_setup import logger
from .models import GeneratedPost, PublishResult

SCOPES = ["https://www.googleapis.com/auth/blogger"]


def authorize_blogger() -> Credentials:
    settings = get_settings()
    token_path = settings.google_token_path
    client_secret_path = settings.google_client_secret_path

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not client_secret_path.exists():
            raise FileNotFoundError(
                f"Google OAuth client file not found: {client_secret_path}. "
                "Download it from Google Cloud Console and set GOOGLE_CLIENT_SECRET_FILE."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_blogger_service():
    creds = authorize_blogger()
    return build("blogger", "v3", credentials=creds, cache_discovery=False)


class BloggerPublisher:
    def __init__(self) -> None:
        self.settings = get_settings()

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def publish(self, post: GeneratedPost, as_draft: bool | None = None) -> PublishResult:
        draft = self.settings.blogger_post_as_draft if as_draft is None else as_draft
        if not self.settings.blogger_blog_id:
            return PublishResult(success=False, platform="blogger", error="Missing BLOGGER_BLOG_ID")

        try:
            service = get_blogger_service()
            body = {
                "kind": "blogger#post",
                "blog": {"id": self.settings.blogger_blog_id},
                "title": post.title,
                "content": post.html,
                "labels": post.labels,
                "customMetaData": post.meta_description,
            }
            request = service.posts().insert(
                blogId=self.settings.blogger_blog_id,
                body=body,
                isDraft=draft,
                fetchBody=True,
                fetchImages=True,
            )
            response = request.execute()
            post_id = response.get("id", "")
            url = response.get("url", "")
            logger.info("Published Blogger post %s draft=%s", post_id, draft)
            return PublishResult(
                success=True,
                platform="blogger",
                post_id=post_id,
                url=url,
                response=response,
            )
        except Exception as exc:
            logger.exception("Blogger publish failed: %s", exc)
            return PublishResult(success=False, platform="blogger", error=str(exc))
