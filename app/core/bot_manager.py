from aiogram import Bot
from app.config.settings import settings

# FAqat 2 ta bot bor, boshqa YO‘Q
_BOTS: dict[str, Bot] = {}


def get_bot(account_code: str) -> Bot | None:
    """
    account_code:
      - bot1
      - bot2
    """
    if account_code not in ("bot1", "bot2"):
        return None

    if account_code in _BOTS:
        return _BOTS[account_code]

    if account_code == "bot1":
        token = settings.BOT1_TOKEN
    else:
        token = settings.BOT2_TOKEN

    bot = Bot(token=token)
    _BOTS[account_code] = bot
    return bot
