from aiogram import Bot

from app.utils.formatters import format_sale, format_payment
from app.utils.helpers import normalize_phone
from app.core.bot_manager import get_bot
from app.core.db import get_conn_for_account


async def handle_regos_event(account_code: str, payload: dict):
    bot: Bot = get_bot(account_code)
    if not bot:
        return

    # ✅ REGOS REAL DATA
    event_data = payload.get("data", {})
    action = event_data.get("action")
    data = event_data.get("data", {})

    if not action:
        return

    text = _format_payload(action, data)

    conn = get_conn_for_account(account_code)
    cur = conn.cursor()

    # ✅ GURUHLAR
    cur.execute("SELECT id FROM groups")
    groups = cur.fetchall()
    for (group_id,) in groups:
        await bot.send_message(group_id, text)

    # ✅ USER PHONE (agar bo‘lsa)
    phone = data.get("phone")
    if phone:
        phone = normalize_phone(phone)
        cur.execute("SELECT id FROM users WHERE phone = ?", (phone,))
        user = cur.fetchone()
        if user:
            await bot.send_message(user[0], text)

    conn.close()


def _format_payload(action: str, data: dict) -> str:
    if action == "DocPaymentPerformed":
        return format_payment(data)
    return format_sale(data)
