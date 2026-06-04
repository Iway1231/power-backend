# app/image_loader.py
import httpx
import os
from uuid import uuid4

async def download_image(url: str) -> str:
    os.makedirs("images", exist_ok=True)
    filename = f"images/{uuid4().hex}.jpg"

    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        r.raise_for_status()

        with open(filename, "wb") as f:
            f.write(r.content)

    return filename
