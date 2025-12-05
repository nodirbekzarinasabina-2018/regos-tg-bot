from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    bot1_token: str
    bot2_token: str

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore"   # 🔥 MUHIM
    )

settings = Settings()
