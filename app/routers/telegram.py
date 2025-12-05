from aiogram import Dispatcher, types
from app.handlers.telegram import register_group


def setup(dp: Dispatcher, account_code: str):
    @dp.message_handler(commands=["start"])
    async def start_handler(message: types.Message):
        await register_group(message, account_code)
