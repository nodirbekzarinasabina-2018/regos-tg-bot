from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from app.storage import Storage


def _read_phone_links(source_db: Path, source_bot_key: str | None) -> list[tuple[str, int, str]]:
    con = sqlite3.connect(source_db)
    try:
        query = "SELECT bot_key, phone, chat_id, full_name FROM phone_links"
        params: tuple[object, ...] = ()
        if source_bot_key:
            query += " WHERE bot_key = ?"
            params = (source_bot_key,)
        query += " ORDER BY updated_at DESC"
        rows = con.execute(query, params).fetchall()
    finally:
        con.close()

    result: list[tuple[str, int, str]] = []
    seen_phones: set[str] = set()
    for _, phone, chat_id, full_name in rows:
        phone_str = str(phone or "").strip()
        if not phone_str or phone_str in seen_phones:
            continue
        seen_phones.add(phone_str)
        result.append((phone_str, int(chat_id), str(full_name or "Mijoz")))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Telegram phone links from an old SQLite bot DB.")
    parser.add_argument("--source-db", required=True, help="Path to old bot.db")
    parser.add_argument("--target-db", required=True, help="Path to current bot.db")
    parser.add_argument("--target-bot-key", default="wholesale", help="Bot key to write into the new DB")
    parser.add_argument(
        "--source-bot-key",
        default="",
        help="Optional old bot key filter, for example shared or wholesale",
    )
    args = parser.parse_args()

    source_db = Path(args.source_db).expanduser().resolve()
    target_db = Path(args.target_db).expanduser().resolve()
    if not source_db.exists():
        raise SystemExit(f"Source DB not found: {source_db}")

    storage = Storage(target_db)
    links = _read_phone_links(source_db, args.source_bot_key.strip() or None)
    imported = 0
    for phone, chat_id, full_name in links:
        storage.upsert_phone_link(args.target_bot_key, phone, chat_id, full_name)
        imported += 1

    print(
        f"Imported {imported} phone links from {source_db} "
        f"into {target_db} as bot_key={args.target_bot_key}"
    )


if __name__ == "__main__":
    main()
