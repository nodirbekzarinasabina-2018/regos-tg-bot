from aiogram import Router
from aiogram.types import Message, Contact, ChatMemberUpdated
from aiogram.filters import CommandStart

from app.core.db import get_conn
from app.core.dispatcher import dp
from app.utils.helpers import normalize_phone

router = Router()

# Vaqtincha memory storage
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
    if message.chat.type in ("group", "supergroup"):
        account = _get_account_code(message)
        GROUPS.setdefault(account, set()).add(message.chat.id)

@router.message(lambda m: m.contact is not None)
async def contact_handler(message: Message):
    account = _get_account_code(message)
    phone = normalize_phone(message.contact.phone_number)

    USERS.setdefault(account, {})[phone] = message.from_user.id

    # ✅ DB ga saqlash
    from app.core.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (id, phone) VALUES (?, ?)",
        (message.from_user.id, phone)
    )
    conn.commit()
    conn.close()

    await message.answer("✅ Telefon saqlandi")

def _get_account_code(message: Message) -> str:
    # Hozircha bitta test account
    # Later: router orqali keladi
    return "test"


def register_telegram_handlers():
    dp.include_router(router)
