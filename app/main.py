from fastapi import FastAPI
import asyncio

from app.routers import regos
from app.core.db import init_all
from app.core.dispatcher import start_polling

app = FastAPI(title="Regos Telegram Bots")

@app.on_event("startup")
async def on_startup():
    init_all()
    asyncio.create_task(start_polling())

app.include_router(regos.router)
