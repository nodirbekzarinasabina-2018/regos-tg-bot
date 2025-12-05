import asyncio
from fastapi import FastAPI

from app.config import BOT_A, BOT_B
from app.bot.factory import BotBundle
from app.bot.handlers import router as common_router
from app.webhook.regos import router as regos_router


app = FastAPI()

bots = {}


@app.on_event("startup")
async def startup():
    bots["A"] = BotBundle(token=BOT_A.token, db_path=BOT_A.db_path)
    bots["B"] = BotBundle(token=BOT_B.token, db_path=BOT_B.db_path)

    for bundle in bots.values():
        bundle.dp.include_router(common_router)
        asyncio.create_task(bundle.dp.start_polling(bundle.bot))


app.include_router(regos_router)
