import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.core.bot_manager import get_bot
from app.core.db import get_conn_for_account


def setup_bot(account_code: str, token: str):
    bot = Bot(token=token)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start_handler(message: Message):
        # faqat group / supergroup
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            await message.answer("Bot guruhda /start qilinadi ✅")
            return

        conn = get_conn_for_account(account_code)
        cur = conn.cursor()

        cur.execute(
            "INSERT OR IGNORE INTO groups (id) VALUES (?)",
            (message.chat.id,)
        )

        conn.commit()
        conn.close()

        await message.answer("✅ Guruh ro‘yxatga olindi")

    return bot, dp


async def start_polling():
    tasks = []

    # FAqat 2 ta bot
    for account_code in ("bot1", "bot2"):
        bot = get_bot(account_code)
        if not bot:
            continue

        _, dp = setup_bot(account_code, bot.token)
        tasks.append(dp.start_polling(bot))

    await asyncio.gather(*tasks)
