from __future__ import annotations

from io import BytesIO
import json

import httpx


class TelegramApiError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, bot_token: str, timeout_seconds: int = 20) -> None:
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.timeout_seconds = timeout_seconds

    async def _post(self, method: str, data: dict | None = None, files: dict | None = None) -> dict:
        url = f"{self.base_url}/{method}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, data=data, files=files)
        if resp.status_code >= 300:
            raise TelegramApiError(f"{method} HTTP xato: {resp.status_code} {resp.text}")
        payload = resp.json()
        if not payload.get("ok"):
            raise TelegramApiError(f"{method} Telegram xato: {payload}")
        return payload

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        reply_markup: dict | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        await self.send_message_result(
            chat_id,
            text,
            reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_message_result(
        self,
        chat_id: str | int,
        text: str,
        reply_markup: dict | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict:
        data = {
            "chat_id": str(chat_id),
            "text": text,
            "disable_web_page_preview": "true",
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=True)
        if reply_to_message_id is not None:
            data["reply_to_message_id"] = str(reply_to_message_id)
        payload = await self._post("sendMessage", data=data)
        return payload.get("result", {})

    async def send_photo_bytes(
        self,
        chat_id: str | int,
        photo_bytes: bytes,
        *,
        filename: str = "cheque.png",
        caption: str = "",
    ) -> None:
        photo_buf = BytesIO(photo_bytes)
        files = {"photo": (filename, photo_buf, "image/png")}
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
        await self._post("sendPhoto", data=data, files=files)

    async def send_document_bytes(
        self,
        chat_id: str | int,
        document_bytes: bytes,
        *,
        filename: str = "cheque.pdf",
        caption: str = "",
    ) -> None:
        doc_buf = BytesIO(document_bytes)
        files = {"document": (filename, doc_buf, "application/pdf")}
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
        await self._post("sendDocument", data=data, files=files)

    async def set_webhook(self, webhook_url: str) -> dict:
        return await self._post("setWebhook", data={"url": webhook_url})

    async def copy_message(
        self,
        chat_id: str | int,
        from_chat_id: str | int,
        message_id: int,
        *,
        reply_to_message_id: int | None = None,
    ) -> dict:
        data = {
            "chat_id": str(chat_id),
            "from_chat_id": str(from_chat_id),
            "message_id": str(message_id),
        }
        if reply_to_message_id is not None:
            data["reply_to_message_id"] = str(reply_to_message_id)
        payload = await self._post("copyMessage", data=data)
        return payload.get("result", {})

    async def send_video_note_result(self, chat_id: str | int, file_id: str) -> dict:
        payload = await self._post(
            "sendVideoNote",
            data={
                "chat_id": str(chat_id),
                "video_note": file_id,
            },
        )
        return payload.get("result", {})

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        data = {"callback_query_id": callback_query_id}
        if text:
            data["text"] = text
        await self._post("answerCallbackQuery", data=data)

    async def create_chat_invite_link(
        self,
        chat_id: str | int,
        *,
        name: str = "",
        creates_join_request: bool = False,
        member_limit: int | None = None,
    ) -> dict:
        data = {"chat_id": str(chat_id)}
        if name:
            data["name"] = name
        if creates_join_request:
            data["creates_join_request"] = "true"
        if member_limit is not None:
            data["member_limit"] = str(member_limit)
        payload = await self._post("createChatInviteLink", data=data)
        return payload.get("result", {})

    async def approve_chat_join_request(self, chat_id: str | int, user_id: int) -> None:
        await self._post(
            "approveChatJoinRequest",
            data={"chat_id": str(chat_id), "user_id": str(user_id)},
        )

    async def decline_chat_join_request(self, chat_id: str | int, user_id: int) -> None:
        await self._post(
            "declineChatJoinRequest",
            data={"chat_id": str(chat_id), "user_id": str(user_id)},
        )
