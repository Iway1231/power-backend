import logging

import httpx
from bs4 import BeautifulSoup

from app import config
from app.http_retry import get_with_retry

logger = logging.getLogger(__name__)


async def fetch_latest_posts(limit: int = 20) -> list[dict]:
    logger.info("Fetching Telegram HTML: %s", config.CHANNEL_URL)

    async with httpx.AsyncClient(
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        response = await get_with_retry(
            lambda: client.get(config.CHANNEL_URL),
            retries=config.SETTINGS.upstream_retry_attempts,
            backoff_seconds=config.SETTINGS.upstream_retry_backoff_seconds,
        )

    soup = BeautifulSoup(response.text, "lxml")

    messages = soup.select("div.tgme_widget_message")
    logger.info("Found %d posts", len(messages))

    posts = []

    for msg in messages[:limit]:
        text_el = msg.select_one(".tgme_widget_message_text")
        img_el = msg.select_one("a.tgme_widget_message_photo_wrap")
        date_el = msg.select_one("time[datetime]")

        text = text_el.get_text(" ", strip=True) if text_el else ""
        image = (
            img_el["style"].split("url('")[1].split("')")[0]
            if img_el and "url" in img_el.get("style", "")
            else None
        )
        published_at = date_el["datetime"] if date_el else None

        logger.debug("Post: text=%s image=%s date=%s", text[:80] or "-", image, published_at)

        posts.append(
            {
                "post_id": msg.get("data-post"),
                "text": text,
                "image": image,
                "published_at": published_at,
            }
        )

    return posts
