from aiogram import Bot

from app.core.db import get_conn

# account_code -> Bot mapping
_BOTS: dict[str, Bot] = {}


def get_bot(account_code: str) -> Bot | None:
    # avval cache’dan tekshiramiz
    if account_code in _BOTS:
        return _BOTS[account_code]

    # DB’dan olamiz
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT bot_token, is_active FROM accounts WHERE account_code = ?",
        (account_code,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    bot_token, is_active = row
    if not is_active:
        return None

    bot = Bot(token=bot_token)
    _BOTS[account_code] = bot
    return bot
def reload_bots():
    _BOTS.clear()
