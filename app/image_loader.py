"""Download upstream images safely for OCR processing."""

import os
import tempfile

import httpx

from app import config
from app.http_retry import get_with_retry

MAX_IMAGE_BYTES = 15 * 1024 * 1024


async def download_image(url: str) -> str:
    image_dir = "images"
    os.makedirs(image_dir, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix="power-", suffix=".jpg", dir=image_dir)
    os.close(fd)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.REQUEST_TIMEOUT_SECONDS),
            follow_redirects=True,
        ) as client:
            response = await get_with_retry(
                lambda: client.send(
                    client.build_request("GET", url),
                    stream=True,
                ),
                retries=config.SETTINGS.upstream_retry_attempts,
                backoff_seconds=config.SETTINGS.upstream_retry_backoff_seconds,
            )
            try:
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_IMAGE_BYTES:
                    raise ValueError("Image exceeds the maximum allowed size")

                size = 0
                with open(filename, "wb") as image_file:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_IMAGE_BYTES:
                            raise ValueError("Image exceeds the maximum allowed size")
                        image_file.write(chunk)
            finally:
                await response.aclose()
    except BaseException:
        try:
            os.unlink(filename)
        except FileNotFoundError:
            pass
        raise

    return filename
