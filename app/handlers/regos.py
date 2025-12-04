from aiogram import Bot

from app.utils.formatters import format_sale, format_payment
from app.utils.helpers import normalize_phone
from app.handlers.telegram import GROUPS, USERS


from app.core.db import get_conn
from app.utils.formatters import format_sale, format_payment


async def handle_regos_event(bot, account_code: str, payload: dict):
    text = _format_payload(payload)

    # 1️⃣ DOIM guruhlarga yuboramiz
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM groups")
    group_ids = cur.fetchall()

    for (group_id,) in group_ids:
        await bot.send_message(group_id, text)

    # 2️⃣ AGAR telefon bo'lsa — shaxsiyga HAM yuboramiz
    phone = payload.get("phone")
    if phone:
        cur.execute(
            "SELECT id FROM users WHERE phone = ?",
            (phone,)
        )
        row = cur.fetchone()
        if row:
            user_id = row[0]
            await bot.send_message(user_id, text)

    conn.close()


def _format_payload(payload: dict) -> str:
    if payload.get("event") == "DocPaymentPerformed":
        return format_payment(payload)
    return format_sale(payload)
