from aiogram import Bot
from app.storage import ACCOUNTS

_bots = {}  # account_code -> Bot


def get_bot(account_code: str):
    if account_code not in ACCOUNTS:
        return None

    if account_code not in _bots:
        _bots[account_code] = Bot(token=ACCOUNTS[account_code])

    return _bots[account_code]
