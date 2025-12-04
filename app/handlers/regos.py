from aiogram import Bot

from utils.formatters import format_sale, format_payment
from utils.helpers import normalize_phone
from handlers.telegram import GROUPS, USERS


async def handle_regos_event(
    *,
    bot: Bot,
    account_code: str,
    payload: dict
):
    """
    Regos webhook core handler
    """

    event = payload.get("event") or payload.get("type")

    # Telefon bo‘lsa — personal yuboramiz
    phone_raw = payload.get("phone") or payload.get("partner_phone")
    phone = normalize_phone(phone_raw) if phone_raw else None

    # Xabar matni
    text: str | None = None

    if event in ("DocWholeSalePerformed", "SALE"):
        text = format_sale(payload)

    elif event in ("DocPaymentPerformed", "PAYMENT"):
        text = format_payment(payload)

    if not text:
        return

    # 1️⃣ Agar telefon bo‘lsa → faqat o‘sha odam
    if phone and phone in USERS.get(account_code, {}):
        user_id = USERS[account_code][phone]
        await bot.send_message(user_id, text)
        return

    # 2️⃣ Aks holda → guruh(lar)
    for group_id in GROUPS.get(account_code, set()):
        await bot.send_message(group_id, text)
