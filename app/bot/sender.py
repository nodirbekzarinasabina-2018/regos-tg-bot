from aiogram import Bot


async def send_to_groups(bot: Bot, group_ids: list[int], text: str):
    for gid in group_ids:
        try:
            await bot.send_message(gid, text)
        except Exception:
            pass


async def send_to_private(bot: Bot, phone: str | None, text: str):
    # Hozircha faqat placeholder
    # Keyin phone -> user_id mapping qilamiz
    return
