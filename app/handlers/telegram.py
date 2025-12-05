from aiogram import Dispatcher, types
from aiogram.filters import CommandStart, Contact
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from app.core.db import get_conn_for_account
from app.utils.helpers import normalize_phone


def register_handlers(dp: Dispatcher, account_code: str):

    @dp.message(CommandStart())
    async def start_handler(message: types.Message):
        conn = get_conn_for_account(account_code)
        cur = conn.cursor()

        # ✅ GURUH
        if message.chat.type in ("group", "supergroup"):
            cur.execute(
                "INSERT OR IGNORE INTO groups (id) VALUES (?)",
                (message.chat.id,)
            )
            conn.commit()
            conn.close()
            await message.reply("✅ Guruh ro‘yxatga olindi")
            return

        # ✅ SHAXSIY CHAT → TELEFON SO‘RAYMIZ
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        conn.close()
        await message.answer(
            "Davom etish uchun telefon raqamingizni yuboring 👇",
            reply_markup=kb
        )

    # ✅ CONTACT HANDLER (TO‘G‘RI FILTER)
    @dp.message(Contact())
    async def contact_handler(message: types.Message):
        phone = normalize_phone(message.contact.phone_number)

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
            reply_markup=ReplyKeyboardRemove()
        )
