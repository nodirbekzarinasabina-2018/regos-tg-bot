from aiogram import Bot
from app.config.settings import settings

_bots: dict[str, Bot] = {}


def get_bot(account_code: str) -> Bot | None:
    if account_code not in settings.accounts:
        return None

    if account_code not in _bots:
        token = settings.accounts[account_code].telegram_token
        _bots[account_code] = Bot(token=token)

    return _bots[account_code]
