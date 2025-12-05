import httpx
from app.config.settings import settings


async def get_doc_wholesale(doc_id: int):
    url = f"{settings.REGOS_URL}/DocWholeSale/Get"
    params = {"id": doc_id}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


async def get_doc_payment(doc_id: int):
    url = f"{settings.REGOS_URL}/DocPayment/Get"
    params = {"id": doc_id}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()
