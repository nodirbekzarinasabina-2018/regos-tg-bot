from pydantic import BaseModel


class Settings(BaseModel):
    # keyinchalik qo‘shamiz:
    # admin_username: str
    # admin_password: str
    # secret_key: str
    pass


settings = Settings()
