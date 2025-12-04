from fastapi import FastAPI, Request, HTTPException
from aiogram import Dispatcher
from aiogram.types import Update

from app.bot_manager import get_bot

app = FastAPI(title="Regos Multi Bot")
dp = Dispatcher()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tg/{account_code}")
async def telegram_webhook(account_code: str, request: Request):
    bot = get_bot(account_code)
    if not bot:
        raise HTTPException(status_code=404, detail="Unknown account")

    body = await request.body()
    update = Update.model_validate_json(body)

    await dp.feed_update(bot, update)
    return {"ok": True}
