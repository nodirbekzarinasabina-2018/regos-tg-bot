from aiogram import Dispatcher, types
from aiogram.filters import CommandStart

from app.core.db import get_conn_for_account
from app.utils.helpers import normalize_phone


def register_handlers(dp: Dispatcher, account_code: str):
    """
    Har bir bot uchun handlerlarni ro‘yxatdan o‘tkazamiz
    """

    @dp.message(CommandStart())
    async def start_handler(message: types.Message):
        conn = get_conn_for_account(account_code)
        cur = conn.cursor()

        # ✅ GURUH / SUPERGURUH
        if message.chat.type in ("group", "supergroup"):
            cur.execute(
                "INSERT OR IGNORE INTO groups (id) VALUES (?)",
                (message.chat.id,)
            )
            conn.commit()
            await message.reply("✅ Guruh ro‘yxatga olindi")

        # ✅ SHAXSIY CHAT
        elif message.chat.type == "private":
            user_id = message.from_user.id

            # Telegram phone majburiy bermaydi
            phone = None
            if message.from_user.username:
                phone = normalize_phone(message.from_user.username)

            cur.execute(
                "INSERT OR IGNORE INTO users (id, phone) VALUES (?, ?)",
                (user_id, phone)
            )
            conn.commit()
            await message.reply("✅ Siz ro‘yxatdan o‘tdingiz")

        conn.close()
