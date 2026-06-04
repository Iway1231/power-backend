import httpx
from bs4 import BeautifulSoup

CHANNEL_URL = "https://t.me/s/nya_merezhi"


async def fetch_latest_posts(limit: int = 20) -> list[dict]:
    print("🔗 FETCH HTML:", CHANNEL_URL)

    async with httpx.AsyncClient() as client:
        r = await client.get(CHANNEL_URL)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    messages = soup.select("div.tgme_widget_message")
    print(f"📦 FOUND POSTS: {len(messages)}")

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

        print(f"\n🧾 POST #{idx}")
        print("📩 TEXT:", text[:200] or "—")
        print("🖼 IMAGE:", image)

        posts.append({
            "text": text,
            "image": image
        })

    return posts
