from fastapi import APIRouter, Request, HTTPException
from app.config import BOT_A, BOT_B
from app.bot.factory import BotBundle

router = APIRouter()


def detect_account(request: Request):
    token = request.headers.get("Authorization")
    if token == f"Bearer {BOT_A.regos_token}":
        return "A"
    if token == f"Bearer {BOT_B.regos_token}":
        return "B"
    return None


@router.post("/regos/webhook")
async def regos_webhook(request: Request):
    account = detect_account(request)
    if not account:
        raise HTTPException(status_code=401, detail="UNKNOWN REGOS")

    body = await request.json()
    text = f"🧾 Yangi savdo:\n{body}"

    if account == "A":
        return {"send": "A"}  # yuborishni keyin ulaymiz
    else:
        return {"send": "B"}
from app.bot.sender import send_to_groups

from main import bots  # botlar dict

@router.post("/regos/webhook")
async def regos_webhook(request: Request):
    account = detect_account(request)
    if not account:
        raise HTTPException(status_code=401, detail="UNKNOWN REGOS")

    data = await request.json()

    text = (
        "🧾 Yangi savdo\n"
        f"ID: {data.get('id')}\n"
        f"Summa: {data.get('total')}"
    )

    bundle = bots[account]
    group_ids = bundle.db.get_groups()

    await send_to_groups(bundle.bot, group_ids, text)

    return {"status": "sent"}
