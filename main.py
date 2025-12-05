import asyncio

from app.config import BOT_A, BOT_B
from app.bot.factory import BotBundle
from app.bot.handlers import router as common_router


async def run_bot(bundle: BotBundle):
    bundle.dp.include_router(common_router)
    await bundle.dp.start_polling(bundle.bot)


async def main():
    bot_a = BotBundle(
        token=BOT_A.token,
        db_path=BOT_A.db_path,
    )

    bot_b = BotBundle(
        token=BOT_B.token,
        db_path=BOT_B.db_path,
    )

    await asyncio.gather(
        run_bot(bot_a),
        run_bot(bot_b),
    )


if __name__ == "__main__":
    asyncio.run(main())
