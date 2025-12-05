from aiogram import Bot

from app.config.settings import settings
from app.core.db import get_conn_for_account


async def handle_regos_event(account_code: str, payload: dict):
    # ✅ qaysi bot ishlatamiz
    if account_code == "bot1":
        bot = Bot(settings.bot1_token)
    elif account_code == "bot2":
        bot = Bot(settings.bot2_token)
    else:
        return

    text = "🧾 REGOS HODISA\n\n" + str(payload)

    conn = get_conn_for_account(account_code)
    cur = conn.cursor()

    # ✅ faqAT shU bot guruhlari
    cur.execute("SELECT id FROM groups")
    groups = cur.fetchall()

    for (group_id,) in groups:
        await bot.send_message(group_id, text)

    # ✅ shAxSiy xabar
    phone = payload.get("phone")
    if phone:
        cur.execute(
            "SELECT id FROM users WHERE phone = ?",
            (phone,)
        )
        row = cur.fetchone()
        if row:
            await bot.send_message(row[0], text)

    conn.close()
