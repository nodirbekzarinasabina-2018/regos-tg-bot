import asyncio
from aiogram import Bot, Dispatcher

from app.config.settings import settings

BOTS = {}
TASKS = {}


async def start_bot(account_code: str):
    if account_code in TASKS:
        return

    if account_code == "bot1":
        token = settings.bot1_token
    elif account_code == "bot2":
        token = settings.bot2_token
    else:
        return

    bot = Bot(token=token)
    dp = Dispatcher()

    from app.handlers.telegram import register_handlers
    register_handlers(dp, account_code)

    async def runner():
        await dp.start_polling(bot)

    task = asyncio.create_task(runner())

    BOTS[account_code] = bot
    TASKS[account_code] = task


async def stop_all_bots():
    for task in TASKS.values():
        task.cancel()
