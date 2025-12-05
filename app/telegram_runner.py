import asyncio
from aiogram import Bot, Dispatcher
from app.config.settings import settings
from app.handlers.telegram import register_handlers

async def start_bot(token: str, code: str):
    bot = Bot(token)
    dp = Dispatcher()
    register_handlers(dp, code)
    await dp.start_polling(bot)

async def main():
    await asyncio.gather(
        start_bot(settings.bot1_token, "bot1"),
        start_bot(settings.bot2_token, "bot2"),
    )

if __name__ == "__main__":
    asyncio.run(main())
