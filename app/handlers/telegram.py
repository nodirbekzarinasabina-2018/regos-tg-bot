from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

from app.core.dispatcher import dp
from app.utils.helpers import normalize_phone
from app.core.db import get_conn

router = Router()

# Vaqtincha xotiradagi storage
GROUPS: dict[str, set[int]] = {}
USERS: dict[str, dict[str, int]] = {}


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "✅ Bot ishlayapti.\n"
        "Telefonni yuborish uchun tugmani bosing."
    )


@router.message()
async def group_detect(message: Message):
    # faqat guruhlarda saqlaymiz
    if message.chat.type in ("group", "supergroup"):
        account = _get_account_code(message)
        GROUPS.setdefault(account, set()).add(message.chat.id)


# 1) Contact yuborilgan bo'lsa
@router.message(lambda m: m.contact is not None)
async def contact_from_button(message: Message):
    if message.chat.type != "private":
        return

    account = _get_account_code(message)
    raw_phone = message.contact.phone_number
    phone = normalize_phone(raw_phone)

    _save_phone(account, phone, message.from_user.id)
    await message.answer("✅ Telefon saqlandi (contact)")


# 2) Oddiy matn bilan raqam yozilgan bo'lsa
@router.message(lambda m: m.text is not None and any(ch.isdigit() for ch in m.text))
async def contact_from_text(message: Message):
    if message.chat.type != "private":
        return

    account = _get_account_code(message)
    raw_phone = message.text
    phone = normalize_phone(raw_phone)

    _save_phone(account, phone, message.from_user.id)
    await message.answer("✅ Telefon saqlandi (matn)")


def _save_phone(account: str, phone: str, user_id: int):
    # xotirada
    USERS.setdefault(account, {})[phone] = user_id

    # DB da
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (id, phone) VALUES (?, ?)",
        (user_id, phone)
    )
    conn.commit()
    conn.close()


def _get_account_code(message: Message) -> str:
    # Hozircha bitta test account
    return "test"


def register_telegram_handlers():
    dp.include_router(router)
