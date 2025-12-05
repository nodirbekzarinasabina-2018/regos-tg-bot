import os


class BotConfig:
    def __init__(self, *, token, regos_base_url, regos_token, db_path):
        self.token = token
        self.regos_base_url = regos_base_url
        self.regos_token = regos_token
        self.db_path = db_path


BOT_A = BotConfig(
    token=os.getenv("BOT_A_TOKEN"),
    regos_base_url=os.getenv("REGOS_A_BASE_URL"),
    regos_token=os.getenv("REGOS_A_TOKEN"),
    db_path=os.getenv("DB_A_PATH", "db_a.sqlite3"),
)

BOT_B = BotConfig(
    token=os.getenv("BOT_B_TOKEN"),
    regos_base_url=os.getenv("REGOS_B_BASE_URL"),
    regos_token=os.getenv("REGOS_B_TOKEN"),
    db_path=os.getenv("DB_B_PATH", "db_b.sqlite3"),
)
