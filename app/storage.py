import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PhoneLink:
    bot_key: str
    phone: str
    chat_id: int
    full_name: str
    updated_at: str


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id TEXT PRIMARY KEY,
                    event_action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cur = con.execute("PRAGMA table_info(processed_events)")
            existing_columns = {str(row[1]) for row in cur.fetchall()}
            if "status" not in existing_columns:
                con.execute("ALTER TABLE processed_events ADD COLUMN status TEXT NOT NULL DEFAULT 'processed'")

            con.execute(
                """
                CREATE TABLE IF NOT EXISTS phone_links (
                    bot_key TEXT NOT NULL DEFAULT 'shared',
                    phone TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    full_name TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (bot_key, phone)
                )
                """
            )
            cur = con.execute("PRAGMA table_info(phone_links)")
            phone_columns = {str(row[1]) for row in cur.fetchall()}
            if "bot_key" not in phone_columns:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS phone_links_v2 (
                        bot_key TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        chat_id INTEGER NOT NULL,
                        full_name TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (bot_key, phone)
                    )
                    """
                )
                con.execute(
                    """
                    INSERT OR REPLACE INTO phone_links_v2 (bot_key, phone, chat_id, full_name, updated_at)
                    SELECT 'shared', phone, chat_id, full_name, updated_at
                    FROM phone_links
                    """
                )
                con.execute("DROP TABLE phone_links")
                con.execute("ALTER TABLE phone_links_v2 RENAME TO phone_links")

            con.execute(
                """
                CREATE TABLE IF NOT EXISTS debt_snapshots (
                    entity_key TEXT PRIMARY KEY,
                    debt_amount REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_documents (
                    doc_kind TEXT NOT NULL,
                    doc_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (doc_kind, doc_id)
                )
                """
            )
            con.commit()

    def try_start_event(self, event_id: str, event_action: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                """
                INSERT OR IGNORE INTO processed_events (event_id, event_action, status, created_at)
                VALUES (?, ?, 'processing', ?)
                """,
                (event_id, event_action, _utc_now_iso()),
            )
            con.commit()
            return cur.rowcount == 1

    def get_event_status(self, event_id: str) -> Optional[str]:
        with self._connect() as con:
            cur = con.execute("SELECT status FROM processed_events WHERE event_id = ? LIMIT 1", (event_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return str(row[0])

    def mark_processed(self, event_id: str, event_action: str) -> None:
        with self._connect() as con:
            con.execute(
                """
                UPDATE processed_events
                SET event_action = ?, status = 'processed'
                WHERE event_id = ?
                """,
                (event_action, event_id),
            )
            con.commit()

    def release_event(self, event_id: str) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM processed_events WHERE event_id = ?", (event_id,))
            con.commit()

    def upsert_phone_link(self, bot_key: str, phone: str, chat_id: int, full_name: str) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO phone_links (bot_key, phone, chat_id, full_name, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(bot_key, phone) DO UPDATE SET
                    chat_id=excluded.chat_id,
                    full_name=excluded.full_name,
                    updated_at=excluded.updated_at
                """,
                (bot_key, phone, chat_id, full_name, _utc_now_iso()),
            )
            con.commit()

    def get_chat_id_by_phone(self, bot_key: str, phone: str) -> Optional[int]:
        with self._connect() as con:
            cur = con.execute(
                "SELECT chat_id FROM phone_links WHERE bot_key = ? AND phone = ? LIMIT 1",
                (bot_key, phone),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return int(row[0])

    def get_phone_link(self, bot_key: str, phone: str) -> Optional[PhoneLink]:
        with self._connect() as con:
            cur = con.execute(
                """
                SELECT bot_key, phone, chat_id, full_name, updated_at
                FROM phone_links
                WHERE bot_key = ? AND phone = ?
                LIMIT 1
                """,
                (bot_key, phone),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return PhoneLink(
                bot_key=str(row[0]),
                phone=str(row[1]),
                chat_id=int(row[2]),
                full_name=str(row[3]),
                updated_at=str(row[4]),
            )

    def get_phone_link_by_chat_id(self, bot_key: str, chat_id: int) -> Optional[PhoneLink]:
        with self._connect() as con:
            cur = con.execute(
                """
                SELECT bot_key, phone, chat_id, full_name, updated_at
                FROM phone_links
                WHERE bot_key = ? AND chat_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (bot_key, chat_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return PhoneLink(
                bot_key=str(row[0]),
                phone=str(row[1]),
                chat_id=int(row[2]),
                full_name=str(row[3]),
                updated_at=str(row[4]),
            )

    def set_debt_snapshot(self, entity_key: str, debt_amount: float) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO debt_snapshots (entity_key, debt_amount, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(entity_key) DO UPDATE SET
                    debt_amount=excluded.debt_amount,
                    updated_at=excluded.updated_at
                """,
                (entity_key, debt_amount, _utc_now_iso()),
            )
            con.commit()

    def get_debt_snapshot(self, entity_key: str) -> Optional[float]:
        with self._connect() as con:
            cur = con.execute(
                "SELECT debt_amount FROM debt_snapshots WHERE entity_key = ? LIMIT 1",
                (entity_key,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return float(row[0])

    def is_document_processed(self, doc_kind: str, doc_id: int) -> bool:
        with self._connect() as con:
            cur = con.execute(
                """
                SELECT status
                FROM processed_documents
                WHERE doc_kind = ? AND doc_id = ?
                LIMIT 1
                """,
                (doc_kind, doc_id),
            )
            row = cur.fetchone()
            return row is not None and str(row[0]) == "processed"

    def mark_document_processed(self, doc_kind: str, doc_id: int) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO processed_documents (doc_kind, doc_id, status, updated_at)
                VALUES (?, ?, 'processed', ?)
                ON CONFLICT(doc_kind, doc_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (doc_kind, doc_id, _utc_now_iso()),
            )
            con.commit()
