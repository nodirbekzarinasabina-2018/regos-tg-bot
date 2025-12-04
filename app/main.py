from fastapi import FastAPI

from app.routers.telegram import router as telegram_router
from app.routers.regos import router as regos_router

app = FastAPI(title="Regos Multi Bot", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


# Routers
app.include_router(telegram_router)
app.include_router(regos_router)
