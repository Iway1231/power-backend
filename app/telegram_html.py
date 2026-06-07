import httpx
from bs4 import BeautifulSoup

from app import config


async def fetch_latest_posts(limit: int = 20) -> list[dict]:
    print("FETCH HTML:", config.CHANNEL_URL)

    async with httpx.AsyncClient() as client:
        response = await client.get(config.CHANNEL_URL)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    messages = soup.select("div.tgme_widget_message")
    print(f"FOUND POSTS: {len(messages)}")

    posts = []

    for idx, msg in enumerate(messages[:limit], start=1):
        text_el = msg.select_one(".tgme_widget_message_text")
        img_el = msg.select_one("a.tgme_widget_message_photo_wrap")

        text = text_el.get_text(" ", strip=True) if text_el else ""
        image = (
            img_el["style"].split("url('")[1].split("')")[0]
            if img_el and "url" in img_el.get("style", "")
            else None
        )

        print(f"POST #{idx}")
        print("TEXT:", text[:200] or "-")
        print("IMAGE:", image)

        posts.append({
            "text": text,
            "image": image,
        })

    return posts
