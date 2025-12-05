from fastapi import FastAPI

from app.routers import regos
from app.core.db import init_all
from app.core.bot_manager import start_bot

app = FastAPI(title="Regos Telegram Bots")


@app.on_event("startup")
async def on_startup():
    # ✅ DB’LARNI OCHAMIZ
    init_all()

    # ✅ IKKALA BOTNI ISHGA TUSHURAMIZ
    await start_bot("bot1")
    await start_bot("bot2")


# ✅ ROUTER
app.include_router(regos.router)
