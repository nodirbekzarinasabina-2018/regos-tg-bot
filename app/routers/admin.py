from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.db import get_conn

router = APIRouter(prefix="/admin", tags=["admin"])


class AccountIn(BaseModel):
    account_code: str
    bot_token: str
    is_active: bool = True


@router.post("/accounts")
def add_account(data: AccountIn):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO accounts (account_code, bot_token, is_active) VALUES (?, ?, ?)",
            (data.account_code, data.bot_token, int(data.is_active))
        )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
    return {"ok": True}


@router.get("/accounts")
def list_accounts():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT account_code, is_active FROM accounts")
    rows = cur.fetchall()
    conn.close()
    return rows
from app.core.bot_manager import reload_bots


@router.post("/reload")
def reload_tokens():
    reload_bots()
    return {"ok": True}
@router.put("/accounts/{account_code}")
def update_account(account_code: str, data: AccountIn):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE accounts
        SET bot_token = ?, is_active = ?
        WHERE account_code = ?
        """,
        (data.bot_token, int(data.is_active), account_code)
    )
    conn.commit()
    conn.close()

    return {"ok": True}
