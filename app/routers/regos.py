from fastapi import APIRouter, Request, HTTPException

from app.core.bot_manager import get_bot
from app.handlers.regos import handle_regos_event

router = APIRouter(prefix="/regos", tags=["regos"])


@router.post("/{account_code}")
async def regos_webhook(account_code: str, request: Request):
    bot = get_bot(account_code)
    if not bot:
        raise HTTPException(status_code=404, detail="Unknown account")

    payload = await request.json()

    await handle_regos_event(
        bot=bot,
        account_code=account_code,
        payload=payload
    )

    return {"ok": True}
