from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from app.db import Database


class BotBundle:
    def __init__(self, *, token: str, db_path: str):
        self.bot = Bot(token=token, parse_mode=ParseMode.HTML)
        self.dp = Dispatcher()
        self.db = Database(db_path=db_path)
