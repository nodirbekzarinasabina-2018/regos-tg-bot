from aiogram import Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from app.core.db import get_conn_for_account
from app.utils.helpers import normalize_phone


def register_handlers(dp: Dispatcher, account_code: str):

    @dp.message(CommandStart())
    async def start_handler(message: types.Message):
        conn = get_conn_for_account(account_code)
        cur = conn.cursor()

        if message.chat.type in ("group", "supergroup"):
            cur.execute(
                "INSERT OR IGNORE INTO groups (id) VALUES (?)",
                (message.chat.id,)
            )
            conn.commit()
            await message.reply("✅ Guruh ro‘yxatga olindi")
            conn.close()
            return

        # ✅ SHAXSIY CHAT
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await message.answer(
            "Davom etish uchun telefon raqamingizni yuboring 👇",
            reply_markup=kb
        )

        conn.close()
    @dp.message(lambda m: m.contact is not None)
    async def contact_handler(message: types.Message):
        contact = message.contact
        phone = normalize_phone(contact.phone_number)

        conn = get_conn_for_account(account_code)
        cur = conn.cursor()

        cur.execute(
            "INSERT OR REPLACE INTO users (id, phone) VALUES (?, ?)",
            (message.from_user.id, phone)
        )

        conn.commit()
        conn.close()

        await message.answer(
            "✅ Telefon raqamingiz saqlandi",
            reply_markup=types.ReplyKeyboardRemove()
        )
