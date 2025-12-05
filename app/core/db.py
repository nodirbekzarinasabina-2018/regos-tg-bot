import sqlite3
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def _db_path(account_code: str) -> Path:
    """
    Har bir account uchun alohida DB:
    bot1 -> data/bot1.db
    bot2 -> data/bot2.db
    """
    return DATA_DIR / f"{account_code}.db"


def get_conn_for_account(account_code: str) -> sqlite3.Connection:
    return sqlite3.connect(_db_path(account_code))


def init_db_for_account(account_code: str):
    """
    Har bir bot/account uchun alohida DB struktura
    """
    conn = get_conn_for_account(account_code)
    cur = conn.cursor()

    # USERS (telegram users)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        phone TEXT UNIQUE
    )
    """)

    # GROUPS (telegram groups)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY
    )
    """)

    conn.commit()
    conn.close()


def init_all():
    """
    Faqat 2 ta bot bor – shu yerda ochib qo‘yamiz
    """
    init_db_for_account("bot1")
    init_db_for_account("bot2")
