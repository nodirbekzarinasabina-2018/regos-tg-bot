from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx


class RegosApiError(RuntimeError):
    pass


@dataclass
class OAuthToken:
    access_token: str
    expires_at: datetime


class RegosClient:
    def __init__(
        self,
        *,
        base_url: str,
        integration_key: str,
        timeout_seconds: int,
        use_oauth: bool = False,
        token_url: str = "",
        client_id: str = "",
        client_secret: str = "",
        oauth_scope: str = "",
    ) -> None:
        clean_base = base_url.rstrip("/")
        if clean_base.endswith("/v1"):
            self.api_url = clean_base
        elif integration_key:
            base_with_key = clean_base if clean_base.endswith(f"/{integration_key}") else f"{clean_base}/{integration_key}"
            self.api_url = f"{base_with_key}/v1"
        else:
            self.api_url = f"{clean_base}/v1"
        self.timeout_seconds = timeout_seconds
        self.use_oauth = use_oauth
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_scope = oauth_scope
        self._token: Optional[OAuthToken] = None

    async def _get_oauth_token(self) -> str:
        if not self.use_oauth:
            return ""

        if self._token and self._token.expires_at > datetime.now(timezone.utc):
            return self._token.access_token

        if not self.client_id or not self.client_secret or not self.token_url:
            raise RegosApiError("OAuth yoqilgan, lekin client_id/client_secret/token_url yo'q.")

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if self.oauth_scope:
            data["scope"] = self.oauth_scope

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(self.token_url, data=data)

        if resp.status_code >= 300:
            raise RegosApiError(f"OAuth token olish xatosi: {resp.status_code} {resp.text}")

        payload = resp.json()
        access_token = payload.get("access_token", "")
        expires_in = int(payload.get("expires_in", 1800))
        if not access_token:
            raise RegosApiError("OAuth token javobida access_token topilmadi.")

        self._token = OAuthToken(
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=max(expires_in - 60, 60)),
        )
        return access_token

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        token = await self._get_oauth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"{self.api_url}/{method.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code >= 300:
            raise RegosApiError(f"{method} xatosi: {resp.status_code} {resp.text}")

        body = resp.json()
        if body.get("ok") is False:
            raise RegosApiError(f"{method} business xatosi: {body}")
        return body

    async def get_doc_wholesale(self, doc_id: int) -> dict[str, Any]:
        body = await self._post("DocWholeSale/Get", {"ids": [doc_id], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"DocWholeSale/Get bo'sh qaytdi. id={doc_id}")
        return items[0]

    async def get_wholesale_operations(self, doc_id: int) -> list[dict[str, Any]]:
        body = await self._post(
            "WholeSaleOperation/Get",
            {"document_ids": [doc_id], "limit": 1000, "offset": 0},
        )
        return body.get("result", [])

    async def get_doc_payment(self, payment_id: int) -> dict[str, Any]:
        body = await self._post("DocPayment/Get", {"ids": [payment_id], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"DocPayment/Get bo'sh qaytdi. id={payment_id}")
        return items[0]

    async def get_doc_purchase(self, doc_id: int) -> dict[str, Any]:
        body = await self._post("DocPurchase/Get", {"ids": [doc_id], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"DocPurchase/Get bo'sh qaytdi. id={doc_id}")
        return items[0]

    async def get_purchase_operations(self, doc_id: int) -> list[dict[str, Any]]:
        body = await self._post(
            "PurchaseOperation/Get",
            {"document_ids": [doc_id], "limit": 1000, "offset": 0},
        )
        return body.get("result", [])

    async def get_doc_returns_to_partner(self, doc_id: int) -> dict[str, Any]:
        body = await self._post("DocReturnsToPartner/Get", {"ids": [doc_id], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"DocReturnsToPartner/Get bo'sh qaytdi. id={doc_id}")
        return items[0]

    async def get_returns_to_partner_operations(self, doc_id: int) -> list[dict[str, Any]]:
        body = await self._post(
            "ReturnsToPartnerOperation/Get",
            {"document_ids": [doc_id], "limit": 1000, "offset": 0},
        )
        return body.get("result", [])

    async def get_doc_wholesale_return(self, doc_id: int) -> dict[str, Any]:
        body = await self._post("DocWholeSaleReturn/Get", {"ids": [doc_id], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"DocWholeSaleReturn/Get bo'sh qaytdi. id={doc_id}")
        return items[0]

    async def get_wholesale_return_operations(self, doc_id: int) -> list[dict[str, Any]]:
        body = await self._post(
            "WholeSaleReturnOperation/Get",
            {"document_ids": [doc_id], "limit": 1000, "offset": 0},
        )
        return body.get("result", [])

    async def get_doc_order_from_partner(self, doc_id: int) -> dict[str, Any]:
        body = await self._post("DocOrderFromPartner/Get", {"ids": [doc_id], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"DocOrderFromPartner/Get bo'sh qaytdi. id={doc_id}")
        return items[0]

    async def get_order_from_partner_operations(self, doc_id: int) -> list[dict[str, Any]]:
        body = await self._post(
            "OrderFromPartnerOperation/Get",
            {"document_ids": [doc_id], "limit": 1000, "offset": 0},
        )
        return body.get("result", [])

    async def get_stocks(self, *, limit: int = 1000, offset: int = 0) -> dict[str, Any]:
        return await self._post("Stock/Get", {"limit": limit, "offset": offset})

    async def get_item_ext(self, *, stock_id: int, limit: int = 1000, offset: int = 0, zero_quantity: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stock_id": stock_id,
            "limit": limit,
            "offset": offset,
            "zero_quantity": zero_quantity,
        }
        return await self._post("Item/GetExt", payload)

    async def get_partners(self, *, limit: int = 1000, offset: int = 0) -> dict[str, Any]:
        return await self._post("Partner/Get", {"limit": limit, "offset": offset})

    async def get_retail_customers(self, *, limit: int = 1000, offset: int = 0) -> dict[str, Any]:
        return await self._post("RetailCustomer/Get", {"limit": limit, "offset": offset})

    async def get_currencies(
        self,
        *,
        limit: int = 1000,
        offset: int = 0,
        search: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"limit": limit, "offset": offset}
        if search:
            payload["search"] = search
        return await self._post("Currency/Get", payload)

    async def get_doc_movement(self, movement_id: int) -> dict[str, Any]:
        body = await self._post("DocMovement/Get", {"ids": [movement_id], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"DocMovement/Get bo'sh qaytdi. id={movement_id}")
        return items[0]

    async def get_movement_operations(self, movement_id: int) -> list[dict[str, Any]]:
        body = await self._post(
            "MovementOperation/Get",
            {"document_ids": [movement_id]},
        )
        return body.get("result", [])

    async def get_pos_cheque(self, cheque_uuid: str) -> dict[str, Any]:
        try:
            body = await self._post("POS/Cheque/Get", {"uuid": cheque_uuid})
            items = body.get("result", [])
            if items:
                return items[0]
        except RegosApiError:
            pass

        body = await self._post("DocCheque/Get", {"uuids": [cheque_uuid], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"POS/Cheque/Get va DocCheque/Get bo'sh qaytdi. uuid={cheque_uuid}")
        return items[0]

    async def get_doc_cheque_operations(self, cheque_uuid: str) -> list[dict[str, Any]]:
        body = await self._post(
            "DocChequeOperation/Get",
            {"doc_sale_uuid": cheque_uuid},
        )
        return body.get("result", [])

    async def get_pos_payments(self, cheque_uuid: str) -> list[dict[str, Any]]:
        try:
            body = await self._post(
                "DocChequePayment/Get",
                {"doc_sale_uuid": cheque_uuid},
            )
            return body.get("result", [])
        except RegosApiError:
            body = await self._post(
                "POS/Payment/Get",
                {"document_uuid": cheque_uuid, "exclude_storno": True},
            )
            return body.get("result", [])

    async def get_retail_customer_debts(self, customer_id: int) -> list[dict[str, Any]]:
        body = await self._post(
            "RetailCustomer/GetDebts",
            {"customer_id": customer_id, "is_debts": True},
        )
        return body.get("result", [])

    async def get_operating_cash(self, operating_cash_id: int) -> dict[str, Any]:
        body = await self._post("OperatingCash/Get", {"ids": [operating_cash_id], "limit": 1, "offset": 0})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"OperatingCash/Get bo'sh qaytdi. id={operating_cash_id}")
        return items[0]

    async def get_pos_session(self, session_uuid: str) -> dict[str, Any]:
        body = await self._post("POS/Session/Get", {"uuid": session_uuid})
        items = body.get("result", [])
        if not items:
            raise RegosApiError(f"POS/Session/Get bo'sh qaytdi. uuid={session_uuid}")
        return items[0]

    async def get_partner_current_balance(self, partner_id: int, firm_id: int | None = None) -> float:
        payload: dict[str, Any] = {"id": partner_id}
        if firm_id:
            payload["firm_id"] = firm_id
        body = await self._post("Partner/GetCurrentBalance", payload)
        return float(body.get("result", 0) or 0)

    async def get_partner_balance_history(
        self,
        *,
        partner_id: int,
        start_date: int,
        end_date: int,
        firm_id: int | None = None,
        currency_id: int | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "partner_id": partner_id,
            "start_date": start_date,
            "end_date": end_date,
        }
        if firm_id:
            payload["firm_id"] = firm_id
        if currency_id:
            payload["currency_id"] = currency_id
        body = await self._post("PartnerBalance/Get", payload)
        return body.get("result", [])
