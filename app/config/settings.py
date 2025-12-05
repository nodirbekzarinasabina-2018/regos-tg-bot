from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot1_token: str
    bot2_token: str
    regos_url: str   # ✅ KICHIK HARF (MUHIM!)

    class Config:
        env_file = ".env"


settings = Settings()
