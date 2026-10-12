# app/image_loader.py
import os
from uuid import uuid4

import httpx

from app import config
from app.http_retry import get_with_retry


async def download_image(url: str) -> str:
    os.makedirs("images", exist_ok=True)
    filename = f"images/{uuid4().hex}.jpg"

    async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT_SECONDS) as client:
        r = await get_with_retry(
            lambda: client.get(url),
            retries=config.SETTINGS.upstream_retry_attempts,
            backoff_seconds=config.SETTINGS.upstream_retry_backoff_seconds,
        )

        with open(filename, "wb") as f:
            f.write(r.content)

    return filename
