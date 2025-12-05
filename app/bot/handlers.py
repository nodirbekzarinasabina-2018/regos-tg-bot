from aiogram import F, Router
from aiogram.types import ChatMemberUpdated

router = Router()


@router.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated):
    chat = event.chat
    if chat.type in ("group", "supergroup"):
        event.framework.db.save_group(
            group_id=chat.id,
            title=chat.title,
        )
