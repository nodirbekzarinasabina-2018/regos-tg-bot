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
        "Telefon raqamingizni shu yerga yozib yuboring (masalan, 998901234567)."
    )


# Guruhlardagi xabarlar uchun: faqat group id saqlaymiz
@router.message(lambda m: m.chat.type in ("group", "supergroup"))
async def group_detect(message: Message):
    account = _get_account_code(message)
    group_id = message.chat.id

    GROUPS.setdefault(account, set()).add(group_id)

    # DB ga yozish
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO groups (id) VALUES (?)",
        (group_id,)
    )
    conn.commit()
    conn.close()



# Shaxsiy chatdagi BARCHA matnlar / contactlar – telefonga hisoblanadi
@router.message()
async def phone_handler(message: Message):
    # faqat private chat
    if message.chat.type != "private":
        return

    # komandalarni ( /start ) e'tiborga olmaymiz
    if message.text and message.text.startswith("/"):
        return

    account = _get_account_code(message)

    # 1) Contact yuborilgan bo'lsa
    if message.contact is not None:
        raw_phone = message.contact.phone_number
    # 2) Oddiy matn bo'lsa
    elif message.text is not None:
        raw_phone = message.text
    else:
        return

    phone = normalize_phone(raw_phone)

    _save_phone(account, phone, message.from_user.id)
    await message.answer(f"✅ Telefon saqlandi: {phone}")


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
