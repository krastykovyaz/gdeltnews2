import asyncio
import os
from telethon import TelegramClient
from telethon.tl.types import Message
from statistics import mean, median
from dotenv import load_dotenv
load_dotenv()

API_ID = int(os.getenv("MTPROTO_API_ID"))
API_HASH = os.getenv("MTPROTO_API_HASH")
SESSION = "stats_session"

CHANNELS = [
    "aidatavibe",
    "openclawrld",
    "clawdbot2026",
    "moltbot2026",
    "blueviperai",
]

POST_LIMIT = 200  # сколько постов анализировать

async def analyze_channel(client, username):
    channel = await client.get_entity(username)
    messages = await client.get_messages(channel, limit=POST_LIMIT)

    views = [m.views for m in messages if m.views is not None]
    forwards = [m.forwards for m in messages if m.forwards is not None]
    reactions = [
        sum(r.count for r in m.reactions.results)
        for m in messages
        if m.reactions and m.reactions.results
    ]

    subs = getattr(channel, "participants_count", None) or 1

    avg_views = mean(views) if views else 0
    med_views = median(views) if views else 0
    avg_forwards = mean(forwards) if forwards else 0
    avg_reactions = mean(reactions) if reactions else 0

    ER = (
        (avg_views + avg_forwards + avg_reactions) / subs
        if avg_views > 0 else 0
    )

    return {
        "channel": username,
        "subscribers": subs,
        "avg_views": avg_views,
        "median_views": med_views,
        "avg_forwards": avg_forwards,
        "avg_reactions": avg_reactions,
        "ER": ER,
    }



async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()

    results = []
    for ch in CHANNELS:
        print(f"📡 Анализируем {ch}...")
        stats = await analyze_channel(client, ch)
        results.append(stats)

    print("\n================= 📊 РЕЗУЛЬТАТЫ =================\n")
    for r in results:
        print(
            f"Канал: {r['channel']}\n"
            f"Подписчики: {r['subscribers']}\n"
            f"Средние просмотры: {r['avg_views']:.0f}\n"
            f"Медиана просмотров: {r['median_views']:.0f}\n"
            f"Средние репосты: {r['avg_forwards']:.2f}\n"
            f"Средние реакции: {r['avg_reactions']:.2f}\n"
            f"ER: {r['ER']:.4f}\n"
            f"{'-'*50}\n"
        )

    # сортировка по ER
    best = max(results, key=lambda x: x["ER"])
    print(f"🏆 ЛУЧШИЙ КАНАЛ: {best['channel']} (ER={best['ER']:.4f})")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
