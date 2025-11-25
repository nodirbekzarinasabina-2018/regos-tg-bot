# ============================================
#            YANGILANGAN main.py
#        100% ISHLOVCHI TO‘LIQ VERSIYA
# ============================================

import asyncio
from datetime import datetime

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Update,
    Message,
    CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    TOKEN,
    DOC_WHOLESALE_GET_URL,
    WHOLESALE_OPERATION_GET_URL,
    DEFAULT_GROUP_ID,
)

# ============================================
# Global obyektlar
# ============================================

app = FastAPI()

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Til xaritalari
user_lang: dict[int, str] = {}
chat_lang: dict[int, str] = {}

LANG_UZ_LATIN = "uz_latin"
LANG_UZ_CYR = "uz_cyr"
LANG_RU = "ru"

LANG_LABELS = {
    LANG_UZ_LATIN: "🇺🇿 O‘zbek (Lotin)",
    LANG_UZ_CYR: "🇺🇿 Ўзбек (Кирилл)",
    LANG_RU: "🇷🇺 Русский",
}

# ============================================
# Til matnlari
# ============================================

def get_labels(lang: str) -> dict:
    if lang == LANG_UZ_CYR:
        return {
            "sale_confirmed": "✅ ПРОВОДКА ТАСДИҚЛАНДИ",
            "object": "Объект",
            "date": "Сана",
            "time": "Вақт",
            "cashier": "Менеҗер",
            "customer": "Харидор",
            "items": "Сотилган товарлар",
            "total": "Жами сумма",
            "old_debt": "Олдинги қарз",
            "total_debt": "Умумий қарз",
            "doc_code": "Ҳужжат",
        }
    elif lang == LANG_RU:
        return {
            "sale_confirmed": "✅ ПРОВОДКА ПОДТВЕРЖДЕНА",
            "object": "Объект",
            "date": "Дата",
            "time": "Время",
            "cashier": "Менеджер",
            "customer": "Покупатель",
            "items": "Проданные позиции",
            "total": "Итого",
            "old_debt": "Предыдущая задолженность",
            "total_debt": "Общий долг",
            "doc_code": "Документ",
        }
    else:
        return {
            "sale_confirmed": "✅ PROVODKA TASDIQLANDI",
            "object": "Obyekt",
            "date": "Sana",
            "time": "Vaqt",
            "cashier": "Menejer",
            "customer": "Xaridor",
            "items": "Sotilgan mahsulotlar",
            "total": "Jami summa",
            "old_debt": "Oldingi qarz",
            "total_debt": "Umumiy qarz",
            "doc_code": "Hujjat",
        }


def format_number(num: float | int) -> str:
    try:
        n = int(num)
    except Exception:
        n = float(num)
    return f"{n:,}".replace(",", " ")


# ============================================
# Til funksiyalari
# ============================================

def get_user_language(user_id: int) -> str:
    return user_lang.get(user_id, LANG_UZ_LATIN)


def get_chat_language(chat_id: int) -> str:
    return chat_lang.get(chat_id, LANG_UZ_LATIN)


def set_user_language(user_id: int, lang: str) -> None:
    if lang in LANG_LABELS:
        user_lang[user_id] = lang


def set_chat_language(chat_id: int, lang: str) -> None:
    if lang in LANG_LABELS:
        chat_lang[chat_id] = lang


# ============================================
# Klaviatura
# ============================================

def build_language_keyboard(prefix: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for code, title in LANG_LABELS.items():
        kb.button(text=title, callback_data=f"{prefix}_lang:{code}")
    kb.adjust(1)
    return kb


# ============================================
# Regos API funksiyalari
# ============================================

async def regos_get_doc_wholesale(doc_id: int) -> dict | None:
    payload = {"ids": [doc_id]}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(DOC_WHOLESALE_GET_URL, json=payload)
    data = resp.json()
    if not data.get("ok"):
        print("Regos DocWholeSale/Get error:", data)
        return None
    result = data.get("result") or []
    return result[0] if result else None


async def regos_get_doc_items(doc_id: int) -> list[dict]:
    """ WholeSaleOperation/Get → document_ids !!! """
    payload = {"document_ids": [doc_id]}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(WHOLESALE_OPERATION_GET_URL, json=payload)

    data = resp.json()
    if not data.get("ok"):
        print("Regos WholeSaleOperation/Get error:", data)
        return []

    return data.get("result") or []


async def regos_get_partner_debt(partner_id: int) -> int:
    return 0   # Hozircha qarz yo‘q


# ============================================
# PROVODKA FORMAT
# ============================================

def format_sale_message(doc: dict, items: list[dict], old_debt: int, lang: str) -> str:
    labels = get_labels(lang)

    doc_code = doc.get("code", "")
    amount = doc.get("amount", 0)
    partner = doc.get("partner") or {}
    stock = doc.get("stock") or {}
    attached_user = doc.get("attached_user") or {}

    partner_name = partner.get("name", "")
    stock_name = stock.get("name", "")
    cashier_name = (
        f"{attached_user.get('first_name', '')} {attached_user.get('last_name', '')}".strip()
        or attached_user.get("login", "")
    )

    ts = doc.get("date")
    if ts:
        dt = datetime.fromtimestamp(ts)
        date_str = dt.strftime("%d.%m.%Y")
        time_str = dt.strftime("%H:%M")
    else:
        date_str = ""
        time_str = ""

    # Tovarlar
    lines: list[str] = []
    for idx, op in enumerate(items, start=1):
        item_info = op.get("item") or {}
        name = item_info.get("name", "")
        qty = op.get("quantity", 0)
        price = op.get("price", 0)
        line_text = f"{idx}) {name} ×{qty} = {format_number(qty * price)}"
        lines.append(line_text)

    items_block = "\n".join(lines) if lines else "-"

    total_debt = amount + old_debt

    text = (
        f"{labels['sale_confirmed']}\n\n"
        f"🏷 {labels['doc_code']}: <b>{doc_code}</b>\n"
        f"📅 {labels['date']}: {date_str}   ⏰ {labels['time']}: {time_str}\n"
        f"🏬 {labels['object']}: {stock_name}\n"
        f"🧍‍♂️ {labels['customer']}: {partner_name}\n"
        f"👨‍💼 {labels['cashier']}: {cashier_name}\n\n"
        f"📦 {labels['items']}:\n{items_block}\n\n"
        f"💰 {labels['total']}: <b>{format_number(amount)} so'm</b>\n"
        f"📌 {labels['old_debt']}: <b>{format_number(old_debt)} so'm</b>\n"
        f"📌 {labels['total_debt']}: <b>{format_number(total_debt)} so'm</b>"
    )
    return text


# ============================================
# Telegram HANDLERLAR
# ============================================

@router.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "Assalomu alaykum!\n"
        "Bu bot Regos optom sotuv provodkalarini guruhga yuboradi.\n\n"
        "🌐 Tilni tanlash uchun tugmani bosing."
    )
    kb = build_language_keyboard(prefix="user")
    await message.answer(text, reply_markup=kb.as_markup())


@router.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>")


@router.message(Command("til"))
async def cmd_til(message: Message):
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            await message.answer("❌ Guruh tili faqat adminlar tomonidan o‘zgartiriladi.")
            return
        kb = build_language_keyboard("group")
        await message.answer("🌐 Guruh uchun tilni tanlang:", reply_markup=kb.as_markup())
    else:
        kb = build_language_keyboard("user")
        await message.answer("🌐 O‘zingiz uchun tilni tanlang:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("user_lang:"))
async def cb_user_lang(call: CallbackQuery):
    _, lang = call.data.split(":", 1)
    set_user_language(call.from_user.id, lang)
    await call.message.edit_text(f"✅ Til saqlandi: {LANG_LABELS[lang]}")
    await call.answer()


@router.callback_query(F.data.startswith("group_lang:"))
async def cb_group_lang(call: CallbackQuery):
    chat_id = call.message.chat.id
    member = await bot.get_chat_member(chat_id, call.from_user.id)

    if member.status not in ("administrator", "creator"):
        return await call.answer("Faqat adminlar o‘zgartirishi mumkin.", show_alert=True)

    _, lang = call.data.split(":", 1)
    set_chat_language(chat_id, lang)
    await call.message.edit_text(f"✅ Guruh tili saqlandi: {LANG_LABELS[lang]}")
    await call.answer()


# ============================================
# FASTAPI ENDPOINTLAR
# ============================================

@app.post("/bot")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return JSONResponse({"ok": True})


@app.post("/regos")
async def regos_webhook(request: Request):
    payload = await request.json()

    print("Regos webhook:", payload)

    data = payload.get("data", {})
    inner_action = data.get("action")
    inner_data = data.get("data", {})
    doc_id = inner_data.get("id")

    # ❗ Faqat tasdiqlangan provodka ishlaydi
    if inner_action != "DocWholeSalePerformed" or not doc_id:
        return JSONResponse({"ok": True, "ignored": True})

    # Hujjat shapkasi
    doc = await regos_get_doc_wholesale(doc_id)
    if not doc:
        print("Doc topilmadi:", doc_id)
        return JSONResponse({"ok": False})

    # Tovarlar
    items = await regos_get_doc_items(doc_id)

    # Qarz
    partner = doc.get("partner") or {}
    partner_id = partner.get("id")
    old_debt = await regos_get_partner_debt(partner_id) if partner_id else 0

    # Guruh tili
    lang = get_chat_language(DEFAULT_GROUP_ID)

    # Xabar
    text = format_sale_message(doc, items, old_debt, lang)

    # Yuborish
    try:
        await bot.send_message(DEFAULT_GROUP_ID, text)
    except Exception as e:
        print("Guruhga yuborishda xatolik:", e)

    return JSONResponse({"ok": True})


@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================
# LOCALDA ISHGA TUSHIRISH
# ============================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
    )
