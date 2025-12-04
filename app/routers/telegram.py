from fastapi import APIRouter, Request, HTTPException
from aiogram.types import Update

from core.bot_manager import get_bot
from core.dispatcher import dp
from handlers.telegram import register_telegram_handlers

router = APIRouter(prefix="/tg", tags=["telegram"])

# handlerlarni bir marta ro‘yxatdan o‘tkazamiz
register_telegram_handlers()


@router.post("/{account_code}")
async def telegram_webhook(account_code: str, request: Request):
    bot = get_bot(account_code)
    if not bot:
        raise HTTPException(status_code=404, detail="Unknown account")

    body = await request.body()
    update = Update.model_validate_json(body)

    await dp.feed_update(bot, update)
    return {"ok": True}
