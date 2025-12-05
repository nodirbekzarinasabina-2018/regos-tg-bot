from aiogram import Bot

from app.utils.formatters import format_sale, format_payment
from app.utils.helpers import normalize_phone

from app.core.bot_manager import get_bot
from app.core.db import get_conn_for_account


async def handle_regos_event(account_code: str, payload: dict):
    bot: Bot = get_bot(account_code)
    if not bot:
        return

    text = _format_payload(payload)

    # ✅ HR ACCOUNT UCHUN ALOHIDA DB CONNECTION
    conn = get_conn_for_account(account_code)
    cur = conn.cursor()

    # ✅ FAQAT SHU ACCOUNT GURUHLARI
    cur.execute(
        "SELECT id FROM groups"
    )
    groups = cur.fetchall()

    for (group_id,) in groups:
        await bot.send_message(group_id, text)

    # ✅ FAQAT SHU ACCOUNT USERI
    phone = payload.get("phone")
    if phone:
        phone = normalize_phone(phone)

        cur.execute(
            "SELECT id FROM users WHERE phone = ?",
            (phone,)
        )
        user = cur.fetchone()
        if user:
            await bot.send_message(user[0], text)

    conn.close()


def _format_payload(payload: dict) -> str:
    if payload.get("event") == "DocPaymentPerformed":
        return format_payment(payload)
    return format_sale(payload)
