from pydantic import BaseModel
from typing import Dict


class AccountSettings(BaseModel):
    telegram_token: str
    regos_webhook_secret: str | None = None


class Settings(BaseModel):
    accounts: Dict[str, AccountSettings] = {}


# ⚠️ HOZIRCHA Vaqtincha
# Keyin buni ENV + DB + Admin panelga o‘tkazamiz
settings = Settings(
    accounts={
        "test": AccountSettings(
            telegram_token="8594792866:AAGVsoyLQH0SX3Wz7EQvV54Eqg7GwlOLXec",
            regos_webhook_secret="test-secret"
        )
    }
)
