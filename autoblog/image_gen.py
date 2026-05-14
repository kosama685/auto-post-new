from __future__ import annotations

import base64
from pathlib import Path

import cloudinary
import cloudinary.uploader
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

from .config import GENERATED_IMAGE_DIR, get_settings
from .logger_setup import logger
from .utils import make_slug


def create_local_placeholder(title: str) -> Path:
    GENERATED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_IMAGE_DIR / f"{make_slug(title)}.png"
    img = Image.new("RGB", (1200, 630), color=(244, 241, 232))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 48)
        small = ImageFont.truetype("DejaVuSans.ttf", 30)
    except Exception:
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    draw.text((70, 180), "الصحة والأعشاب", font=font, fill=(38, 82, 45))
    draw.text((70, 270), title[:60], font=small, fill=(55, 55, 55))
    draw.text((70, 530), "معلومات عامة ولا تغني عن استشارة الطبيب", font=small, fill=(105, 105, 105))
    img.save(path)
    return path


def configure_cloudinary() -> bool:
    settings = get_settings()
    if not settings.has_cloudinary:
        return False
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    return True


def upload_to_cloudinary(path: Path) -> str:
    if not configure_cloudinary():
        return ""
    result = cloudinary.uploader.upload(str(path), folder="arabic-health-blog")
    return result.get("secure_url", "")


def generate_ai_image(title: str) -> Path | None:
    settings = get_settings()
    if not settings.enable_image_generation or not settings.openai_api_key:
        return None
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        prompt = (
            "Professional editorial illustration for an Arabic herbal health blog, "
            "natural herbs, honey, black seed, clean background, no medical claims, "
            f"topic: {title}"
        )
        response = client.images.generate(
            model=settings.openai_image_model,
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        item = response.data[0]
        if getattr(item, "b64_json", None):
            raw = base64.b64decode(item.b64_json)
            path = GENERATED_IMAGE_DIR / f"{make_slug(title)}-ai.png"
            path.write_bytes(raw)
            return path
        # Some image models return a URL. The stable URL lifetime may be limited, so upload if possible elsewhere.
        return None
    except Exception as exc:
        logger.exception("Image generation failed: %s", exc)
        return None


def get_featured_image_url(title: str, existing_url: str = "") -> str:
    settings = get_settings()
    if existing_url and not settings.enable_image_generation:
        return existing_url

    path = generate_ai_image(title) or create_local_placeholder(title)
    uploaded = upload_to_cloudinary(path)
    if uploaded:
        return uploaded
    # Without a public image host, Blogger cannot display a local path. Return original remote image if any.
    return existing_url
