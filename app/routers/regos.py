from fastapi import APIRouter, Request

from app.handlers.regos import handle_regos_event

router = APIRouter(prefix="/regos", tags=["regos"])


@router.post("/{account_code}")
async def regos_webhook(account_code: str, request: Request):
    payload = await request.json()

    await handle_regos_event(
        account_code=account_code,
        payload=payload
    )

    return {"ok": True}

