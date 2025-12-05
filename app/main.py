from fastapi import FastAPI
from app.routers import regos
from app.core.db import init_all

app = FastAPI(title="Regos API")

@app.on_event("startup")
def startup():
    init_all()

app.include_router(regos.router)
