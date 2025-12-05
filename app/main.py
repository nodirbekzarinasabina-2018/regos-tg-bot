from fastapi import FastAPI

from app.routers import regos
from app.core.db import init_all
from app.core.bot_manager import start_bot, stop_all_bots

app = FastAPI(title="Regos Telegram Bots")


@app.on_event("startup")
async def startup():
    init_all()
    await start_bot("bot1")
    await start_bot("bot2")


@app.on_event("shutdown")
async def shutdown():
    await stop_all_bots()


app.include_router(regos.router)
