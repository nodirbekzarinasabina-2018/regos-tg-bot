from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()

def register_handlers(dp, account_code: str):
    dp.include_router(router)


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer("✅ START ISHLADI")
