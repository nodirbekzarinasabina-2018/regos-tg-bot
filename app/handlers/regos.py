from aiogram import Bot

from app.core.bot_manager import get_bot
from app.core.db import get_conn_for_account
from app.utils.helpers import normalize_phone
from app.utils.formatters import format_sale, format_payment
from app.utils.regos_api import get_doc_wholesale, get_doc_payment


async def handle_regos_event(account_code: str, payload: dict):
    bot: Bot = get_bot(account_code)
    if not bot:
        return

    event = payload.get("data", {})
    action = event.get("action")
    data = event.get("data", {})
    doc_id = data.get("id")

    if not action or not doc_id:
        return

    # ✅ REGOS API’DAN TO‘LIQ HUJJATNI OLAMIZ
    if action == "DocWholeSalePerformed":
        doc = await get_doc_wholesale(doc_id)
        text = format_sale(doc)
    elif action == "DocPaymentPerformed":
        doc = await get_doc_payment(doc_id)
        text = format_payment(doc)
    else:
        return

    conn = get_conn_for_account(account_code)
    cur = conn.cursor()

    # ✅ GURUHLAR
    cur.execute("SELECT id FROM groups")
    for (group_id,) in cur.fetchall():
        await bot.send_message(group_id, text)

    # ✅ SHAXSIYGA (AGAR TELEFON BO‘LSA)
    phone = doc.get("phone")
    if phone:
        phone = normalize_phone(phone)
        cur.execute("SELECT id FROM users WHERE phone = ?", (phone,))
        user = cur.fetchone()
        if user:
            await bot.send_message(user[0], text)

    conn.close()
