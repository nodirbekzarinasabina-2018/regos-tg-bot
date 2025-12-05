from fastapi import FastAPI

from app.routers import regos
from app.core.db import init_all

app = FastAPI(title="Regos Telegram Bots")

# ✅ APP STARTIDA DB’LARNI OCHIB OLAMIZ
@app.on_event("startup")
async def on_startup():
    init_all()


# ✅ ROUTERLAR
app.include_router(regos.router)
