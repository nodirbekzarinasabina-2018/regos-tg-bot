from fastapi import APIRouter, Request, HTTPException

from app.handlers.regos import handle_regos_event
from app.core.bot_manager import get_bot

router = APIRouter(prefix="/regos", tags=["regos"])


@router.post("/{account_code}")
async def regos_webhook(account_code: str, request: Request):
    # account mavjudligini tekshiramiz
    if not get_bot(account_code):
        raise HTTPException(status_code=404, detail="Unknown account")

    payload = await request.json()

    await handle_regos_event(
        account_code=account_code,
        payload=payload
    )

    return {"ok": True}
