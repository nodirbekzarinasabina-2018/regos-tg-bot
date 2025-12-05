import asyncio
from aiogram import Bot, Dispatcher

from app.config.settings import settings

# Faqat 2 ta bot bor (qat’iy)
BOTS: dict[str, Bot] = {}
DISPATCHERS: dict[str, Dispatcher] = {}


def get_bot(account_code: str) -> Bot | None:
    """
    account_code:
      - bot1
      - bot2
    """
    return BOTS.get(account_code)


async def start_bot(account_code: str):
    """
    Telegram botni ishga tushuradi (polling bilan)
    """
    if account_code not in ("bot1", "bot2"):
        return

    if account_code in BOTS:
        return  # allaqachon ishlayapti

    # ✅ TOKENNI OLAMIZ
    if account_code == "bot1":
        token = settings.bot1_token
    else:
        token = settings.bot2_token

    bot = Bot(token=token)
    dp = Dispatcher()

    # ✅ HANDLERLARNI ULAYMIZ
    from app.handlers.telegram import register_handlers
    register_handlers(dp, account_code)

    BOTS[account_code] = bot
    DISPATCHERS[account_code] = dp

    # ✅ POLLING START
    asyncio.create_task(dp.start_polling(bot))
