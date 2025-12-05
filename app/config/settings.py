from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT1_TOKEN: str
    BOT2_TOKEN: str
    REGOS_URL: str
    class Config:
        env_file = ".env"


settings = Settings()
