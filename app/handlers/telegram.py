from aiogram import types
from app.core.db import get_conn_for_account


async def register_group(message: types.Message, account_code: str):
    """
    Bot gruppaga qo‘shilganda /start yozilganda
    group_id ni DB ga saqlaydi
    """
    if not message.chat or message.chat.type not in ("group", "supergroup"):
        return

    group_id = message.chat.id

    conn = get_conn_for_account(account_code)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO groups (id) VALUES (?)",
        (group_id,)
    )

    conn.commit()
    conn.close()

    await message.reply("✅ Guruh muvaffaqiyatli ro‘yxatga olindi")
