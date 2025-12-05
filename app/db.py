import sqlite3
from contextlib import contextmanager


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self.get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER UNIQUE NOT NULL,
                    title TEXT
                )
                """
            )

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save_group(self, group_id: int, title: str | None):
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO groups (group_id, title)
                VALUES (?, ?)
                """,
                (group_id, title),
            )

    def get_groups(self) -> list[int]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT group_id FROM groups"
            ).fetchall()
            return [r[0] for r in rows]
