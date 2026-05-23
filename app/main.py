from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app.config import TelegramBotConfig, get_settings
from app.formatting import extract_first_phone, normalize_phone
from app.message_builders import (
    build_purchase_caption,
    build_movement_caption,
    build_payment_caption,
    build_returns_to_partner_caption,
    build_retail_payment_caption,
    build_retail_return_caption,
    build_retail_sale_caption,
    build_sale_caption,
    build_sale_message,
    resolve_wholesale_sale_amount,
    build_session_caption,
    build_wholesale_order_caption,
    build_wholesale_return_caption,
)
from app.regos_client import RegosApiError, RegosClient
from app.rendering import (
    render_purchase_pdf,
    render_movement_pdf,
    render_payment_pdf,
    render_returns_to_partner_pdf,
    render_retail_payment_pdf,
    render_retail_return_pdf,
    render_retail_sale_pdf,
    render_sale_pdf,
    render_session_pdf,
    render_wholesale_order_pdf,
    render_wholesale_return_pdf,
)
from app.storage import Storage
from app.telegram_client import TelegramClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("regos-bot")

settings = get_settings()
settings.temp_dir.mkdir(parents=True, exist_ok=True)

storage = Storage(settings.storage_path)
regos = RegosClient(
    base_url=settings.regos_base_url,
    integration_key=settings.regos_integration_key,
    timeout_seconds=settings.regos_timeout_seconds,
    use_oauth=settings.regos_use_oauth,
    token_url=settings.regos_token_url,
    client_id=settings.regos_client_id,
    client_secret=settings.regos_client_secret,
    oauth_scope=settings.regos_oauth_scope,
)

telegram_clients = {
    key: TelegramClient(config.bot_token)
    for key, config in settings.enabled_bot_configs().items()
}

EVENT_BOT_PREFERENCES = {
    "DocWholeSalePerformed": "wholesale",
    "DocPaymentPerformed": "wholesale",
    "DocWholeSaleReturnPerformed": "wholesale",
    "DocOrderFromPartnerAdded": "wholesale",
    "DocPurchasePerformed": "warehouse",
    "DocReturnsToPartnerPerformed": "warehouse",
    "DocMovementPerformed": "warehouse",
    "DocChequeClosed": "retail",
    "DocSessionOpened": "retail",
    "DocSessionClosed": "retail",
}

app = FastAPI(title=f"{settings.app_brand_name} REGOS Bot", version="2.0.0")


def _any_telegram_enabled() -> bool:
    return bool(telegram_clients)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip())
    return cleaned.strip("_") or "REGOS"


def _document_amount_to_base(amount: float, exchange_rate: float, currency: dict[str, Any] | None) -> float:
    currency = currency or {}
    if bool(currency.get("is_base")) or exchange_rate <= 0:
        return float(amount or 0)
    return float(amount or 0) * exchange_rate


def _base_amount_to_doc_currency(amount_base: float, exchange_rate: float, currency: dict[str, Any] | None) -> float:
    currency = currency or {}
    if bool(currency.get("is_base")) or exchange_rate <= 0:
        return float(amount_base or 0)
    return float(amount_base or 0) / exchange_rate


def _is_private_chat(message: dict[str, Any]) -> bool:
    chat = message.get("chat") or {}
    return str(chat.get("type") or "") == "private"


def _resolve_runtime_bot_config(preferred_key: str) -> TelegramBotConfig:
    return settings.actual_bot_config(preferred_key)


def _resolve_registered_bot_config(bot_key: str) -> TelegramBotConfig:
    config = settings.bot_config(bot_key)
    if not config.enabled:
        raise HTTPException(status_code=404, detail="Bot webhook topilmadi")
    return config


def _get_telegram_client(preferred_key: str) -> tuple[str, TelegramBotConfig, TelegramClient | None]:
    config = _resolve_runtime_bot_config(preferred_key)
    client = telegram_clients.get(config.key)
    return config.key, config, client


def _is_allowed_group_chat(bot_key: str, chat_id: int | str) -> bool:
    _, config, _ = _get_telegram_client(bot_key)
    if not config.group_configured:
        return False
    return str(chat_id) == str(config.group_chat_id)


async def _send_bundle(
    preferred_bot_key: str,
    chat_id: int | str,
    *,
    pdf_bytes: bytes,
    caption: str,
    filename: str,
) -> None:
    actual_bot_key, _, client = _get_telegram_client(preferred_bot_key)
    if client is None:
        logger.info("Telegram client sozlanmagan. bot=%s", actual_bot_key)
        return
    await client.send_document_bytes(chat_id, pdf_bytes, caption=caption, filename=filename)


async def _send_message(
    preferred_bot_key: str,
    chat_id: int | str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    actual_bot_key, _, client = _get_telegram_client(preferred_bot_key)
    if client is None:
        logger.info("Telegram client sozlanmagan. bot=%s", actual_bot_key)
        return

    chunks = _split_telegram_text(text)
    for index, chunk in enumerate(chunks):
        await client.send_message(
            chat_id,
            chunk,
            reply_markup=reply_markup if index == 0 else None,
        )


def _split_telegram_text(text: str, max_length: int = 3500) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0

    for raw_line in text.splitlines():
        line = raw_line or ""
        line_length = len(line) + (1 if current_lines else 0)
        if current_lines and current_length + line_length > max_length:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_length = len(line)
            continue

        if len(line) > max_length:
            if current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = []
                current_length = 0
            for start in range(0, len(line), max_length):
                chunks.append(line[start : start + max_length])
            continue

        current_lines.append(line)
        current_length += line_length

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


def _resolve_partner_phone(partner: dict[str, Any]) -> str:
    phone = partner.get("main_phone") or partner.get("phones") or ""
    return normalize_phone(extract_first_phone(str(phone)))


def _resolve_contact_phone(entity: dict[str, Any]) -> str:
    phone = entity.get("main_phone") or entity.get("phones") or ""
    return normalize_phone(extract_first_phone(str(phone)))


def _retail_customer_snapshot_key(customer: dict[str, Any]) -> str | None:
    customer_id = _safe_int(customer.get("id"))
    if customer_id:
        return f"retail_customer:{customer_id}"
    phone = _resolve_contact_phone(customer)
    if phone:
        return f"retail_phone:{phone}"
    return None


async def _send_to_customer_if_mapped(
    preferred_bot_key: str,
    partner: dict[str, Any],
    *,
    pdf_bytes: bytes,
    caption: str,
    filename: str,
    private_bot_key: str | None = None,
) -> None:
    await _send_to_mapped_phones(
        preferred_bot_key,
        [_resolve_contact_phone(partner)],
        pdf_bytes=pdf_bytes,
        caption=caption,
        filename=filename,
        private_bot_key=private_bot_key,
    )


async def _send_message_to_customer_if_mapped(
    preferred_bot_key: str,
    partner: dict[str, Any],
    *,
    text: str,
    private_bot_key: str | None = None,
) -> None:
    await _send_message_to_mapped_phones(
        preferred_bot_key,
        [_resolve_contact_phone(partner)],
        text=text,
        private_bot_key=private_bot_key,
    )


async def _send_to_mapped_phones(
    preferred_bot_key: str,
    phones: list[str],
    *,
    pdf_bytes: bytes,
    caption: str,
    filename: str,
    private_bot_key: str | None = None,
) -> None:
    if not _any_telegram_enabled():
        logger.info("Telegram hali sozlanmagan. Private xabar yuborish o'tkazib yuborildi.")
        return

    target_bot_key = private_bot_key or preferred_bot_key
    actual_bot_key, _, _ = _get_telegram_client(target_bot_key)
    sent_chat_ids: set[int] = set()
    seen_phones: set[str] = set()

    for raw_phone in phones:
        phone = normalize_phone(extract_first_phone(str(raw_phone or "")))
        if not phone or phone in seen_phones:
            continue
        seen_phones.add(phone)

        chat_id = storage.get_chat_id_by_phone(actual_bot_key, phone)
        if not chat_id:
            logger.info("Private chat_id topilmadi. bot=%s phone=%s", actual_bot_key, phone)
            continue
        if chat_id in sent_chat_ids:
            continue

        await _send_bundle(
            actual_bot_key,
            chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
        sent_chat_ids.add(chat_id)


async def _send_message_to_mapped_phones(
    preferred_bot_key: str,
    phones: list[str],
    *,
    text: str,
    private_bot_key: str | None = None,
) -> None:
    if not _any_telegram_enabled():
        logger.info("Telegram hali sozlanmagan. Private matn yuborish o'tkazib yuborildi.")
        return

    target_bot_key = private_bot_key or preferred_bot_key
    actual_bot_key, _, _ = _get_telegram_client(target_bot_key)
    sent_chat_ids: set[int] = set()
    seen_phones: set[str] = set()

    for raw_phone in phones:
        phone = normalize_phone(extract_first_phone(str(raw_phone or "")))
        if not phone or phone in seen_phones:
            continue
        seen_phones.add(phone)

        chat_id = storage.get_chat_id_by_phone(actual_bot_key, phone)
        if not chat_id:
            logger.info("Private chat_id topilmadi. bot=%s phone=%s", actual_bot_key, phone)
            continue
        if chat_id in sent_chat_ids:
            continue

        await _send_message(actual_bot_key, chat_id, text)
        sent_chat_ids.add(chat_id)


def _preferred_wholesale_private_bot_key() -> str:
    shared = settings.shared_bot_config()
    if shared.enabled:
        return "shared"
    return "wholesale"


def _wholesale_admin_phones() -> list[str]:
    phones: list[str] = []
    seen: set[str] = set()

    for raw_value in [settings.wholesale_admin_phone, "+998907400776"]:
        for part in re.split(r"[,\n;]+", str(raw_value or "")):
            phone = normalize_phone(extract_first_phone(part))
            if not phone or phone in seen:
                continue
            seen.add(phone)
            phones.append(phone)

    return phones


async def process_wholesale_performed(doc_id: int, *, bot_key: str = "wholesale") -> None:
    doc = await regos.get_doc_wholesale(doc_id)
    operations = await regos.get_wholesale_operations(doc_id)

    partner = doc.get("partner") or {}
    firm = doc.get("firm") or {}
    partner_id = _safe_int(partner.get("id"))
    firm_id = _safe_int(firm.get("id"))
    total_debt_base = 0.0
    if partner_id:
        total_debt_base = await regos.get_partner_current_balance(partner_id, firm_id or None)

    currency = doc.get("currency") or {}
    exchange_rate = float(doc.get("exchange_rate") or 0.0)
    sale_amount = resolve_wholesale_sale_amount(doc, operations)
    sale_amount_base = _document_amount_to_base(sale_amount, exchange_rate, currency)
    previous_debt_base = max(total_debt_base - sale_amount_base, 0.0)
    previous_debt_doc_currency = _base_amount_to_doc_currency(previous_debt_base, exchange_rate, currency)
    total_debt_doc_currency = previous_debt_doc_currency + sale_amount

    caption = build_sale_caption(
        doc=doc,
        timezone_name=settings.app_timezone,
        sale_amount=sale_amount,
    )
    sale_text = build_sale_message(
        doc=doc,
        operations=operations,
        sale_amount=sale_amount,
        previous_debt=previous_debt_doc_currency,
        total_debt=total_debt_doc_currency,
        timezone_name=settings.app_timezone,
    )
    company_part = _safe_filename_part((((doc.get("stock") or {}).get("firm") or {}).get("name") or "REGOS"))
    code_part = _safe_filename_part(str(doc.get("code") or doc.get("id") or "savdo"))
    filename = f"{company_part}_Savdo_{code_part}.pdf"
    pdf_bytes = render_sale_pdf(
        doc=doc,
        operations=operations,
        previous_debt_base=previous_debt_base,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if config.enabled and config.group_configured:
        await _send_message(bot_key, config.group_chat_id, sale_text)
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info(
            "Savdo groupga yuborilmadi. bot=%s group_enabled=%s group_configured=%s",
            bot_key,
            settings.wholesale_payment_group_enabled,
            config.group_configured,
        )

    await _send_message_to_customer_if_mapped(
        bot_key,
        partner,
        text=sale_text,
        private_bot_key=_preferred_wholesale_private_bot_key(),
    )
    await _send_to_customer_if_mapped(
        bot_key,
        partner,
        pdf_bytes=pdf_bytes,
        caption=caption,
        filename=filename,
        private_bot_key=_preferred_wholesale_private_bot_key(),
    )
    storage.mark_document_processed("DocWholeSalePerformed", doc_id)


async def process_payment_performed(payment_id: int, *, bot_key: str = "wholesale") -> None:
    payment_doc = await regos.get_doc_payment(payment_id)
    category = payment_doc.get("category") or {}
    if category.get("positive") is False:
        logger.info(
            "DocPaymentPerformed rasxod sifatida o'tkazib yuborildi. id=%s code=%s category_id=%s",
            payment_id,
            payment_doc.get("code"),
            category.get("id"),
        )
        storage.mark_document_processed("DocPaymentPerformed", payment_id)
        return

    partner = payment_doc.get("partner") or {}
    firm = payment_doc.get("firm") or {}
    partner_id = _safe_int(partner.get("id"))
    firm_id = _safe_int(firm.get("id"))

    current_debt = 0.0
    if partner_id:
        current_debt = await regos.get_partner_current_balance(partner_id, firm_id or None)

    payment_amount = float(payment_doc.get("amount") or 0.0)
    payment_currency = (((payment_doc.get("type") or {}).get("account") or {}).get("currency") or {})
    payment_exchange_rate = float(payment_doc.get("exchange_rate") or 0.0)
    payment_amount_base = _document_amount_to_base(payment_amount, payment_exchange_rate, payment_currency)
    previous_debt = current_debt + payment_amount_base
    caption = build_payment_caption(payment_doc=payment_doc, timezone_name=settings.app_timezone)
    company_part = _safe_filename_part(((payment_doc.get("firm") or {}).get("name") or "REGOS"))
    code_part = _safe_filename_part(str(payment_doc.get("code") or payment_doc.get("id") or "tolov"))
    filename = f"{company_part}_Tolov_{code_part}.pdf"
    pdf_bytes = render_payment_pdf(
        payment_doc=payment_doc,
        previous_debt_base=previous_debt,
        current_debt_base=current_debt,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if settings.wholesale_payment_group_enabled and config.enabled and config.group_configured:
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info(
            "To'lov groupga yuborilmadi. bot=%s group_enabled=%s group_configured=%s",
            bot_key,
            settings.wholesale_payment_group_enabled,
            config.group_configured,
        )

    await _send_to_mapped_phones(
        bot_key,
        [
            _resolve_contact_phone(partner),
            *_wholesale_admin_phones(),
        ],
        pdf_bytes=pdf_bytes,
        caption=caption,
        filename=filename,
        private_bot_key=_preferred_wholesale_private_bot_key(),
    )
    storage.mark_document_processed("DocPaymentPerformed", payment_id)


async def process_wholesale_return_performed(doc_id: int, *, bot_key: str = "wholesale") -> None:
    doc = await regos.get_doc_wholesale_return(doc_id)
    operations = await regos.get_wholesale_return_operations(doc_id)

    partner = doc.get("partner") or {}
    stock = doc.get("stock") or {}
    firm = (stock.get("firm") or {}) if not doc.get("firm") else (doc.get("firm") or {})
    partner_id = _safe_int(partner.get("id"))
    firm_id = _safe_int(firm.get("id"))
    current_debt = 0.0
    if partner_id:
        current_debt = await regos.get_partner_current_balance(partner_id, firm_id or None)

    caption = build_wholesale_return_caption(doc=doc, timezone_name=settings.app_timezone)
    company_part = _safe_filename_part(((stock.get("firm") or {}).get("name") or firm.get("name") or "REGOS"))
    code_part = _safe_filename_part(str(doc.get("code") or doc.get("id") or "ulgurji-vozvrat"))
    filename = f"{company_part}_UlgurjiVozvrat_{code_part}.pdf"
    pdf_bytes = render_wholesale_return_pdf(
        doc=doc,
        operations=operations,
        current_debt_base=current_debt,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if config.enabled and config.group_configured:
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)

    await _send_to_customer_if_mapped(
        bot_key,
        partner,
        pdf_bytes=pdf_bytes,
        caption=caption,
        filename=filename,
        private_bot_key=_preferred_wholesale_private_bot_key(),
    )


async def process_order_from_partner_added(doc_id: int, *, bot_key: str = "wholesale") -> None:
    doc = await regos.get_doc_order_from_partner(doc_id)
    operations = await regos.get_order_from_partner_operations(doc_id)

    partner = doc.get("partner") or {}
    stock = doc.get("stock") or {}
    company_part = _safe_filename_part((((stock.get("firm") or {}).get("name")) or "REGOS"))
    caption = build_wholesale_order_caption(doc=doc, timezone_name=settings.app_timezone)
    code_part = _safe_filename_part(str(doc.get("code") or doc.get("id") or "ulgurji-zakaz"))
    filename = f"{company_part}_UlgurjiZakaz_{code_part}.pdf"
    pdf_bytes = render_wholesale_order_pdf(
        doc=doc,
        operations=operations,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if config.enabled and config.group_configured:
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)

    await _send_to_customer_if_mapped(
        bot_key,
        partner,
        pdf_bytes=pdf_bytes,
        caption=caption,
        filename=filename,
        private_bot_key=_preferred_wholesale_private_bot_key(),
    )


async def process_purchase_performed(doc_id: int, *, bot_key: str = "warehouse") -> None:
    doc = await regos.get_doc_purchase(doc_id)
    operations = await regos.get_purchase_operations(doc_id)

    caption = build_purchase_caption(doc=doc, timezone_name=settings.app_timezone)
    company_part = _safe_filename_part((((doc.get("stock") or {}).get("firm") or {}).get("name") or "REGOS"))
    code_part = _safe_filename_part(str(doc.get("code") or doc.get("id") or "postupleniya"))
    filename = f"{company_part}_Postupleniya_{code_part}.pdf"
    pdf_bytes = render_purchase_pdf(
        doc=doc,
        operations=operations,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if config.enabled and config.group_configured:
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)


async def process_returns_to_partner_performed(doc_id: int, *, bot_key: str = "warehouse") -> None:
    doc = await regos.get_doc_returns_to_partner(doc_id)
    operations = await regos.get_returns_to_partner_operations(doc_id)

    caption = build_returns_to_partner_caption(doc=doc, timezone_name=settings.app_timezone)
    company_part = _safe_filename_part((((doc.get("stock") or {}).get("firm") or {}).get("name") or "REGOS"))
    code_part = _safe_filename_part(str(doc.get("code") or doc.get("id") or "vozvrat-kontragentga"))
    filename = f"{company_part}_VozvratKontragentga_{code_part}.pdf"
    pdf_bytes = render_returns_to_partner_pdf(
        doc=doc,
        operations=operations,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if config.enabled and config.group_configured:
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)


async def process_movement_performed(movement_id: int, *, bot_key: str = "warehouse") -> None:
    movement_doc = await regos.get_doc_movement(movement_id)
    operations = await regos.get_movement_operations(movement_id)

    caption = build_movement_caption(
        movement_doc=movement_doc,
        operations=operations,
        timezone_name=settings.app_timezone,
    )
    company_part = _safe_filename_part(
        (
            ((movement_doc.get("stock_sender") or {}).get("firm") or {}).get("name")
            or ((movement_doc.get("stock_receiver") or {}).get("firm") or {}).get("name")
            or "REGOS"
        )
    )
    code_part = _safe_filename_part(str(movement_doc.get("code") or movement_doc.get("id") or "peremisheniya"))
    filename = f"{company_part}_Peremisheniya_{code_part}.pdf"
    pdf_bytes = render_movement_pdf(
        movement_doc=movement_doc,
        operations=operations,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if config.enabled and config.group_configured:
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)


def _sum_retail_open_debts(debts: list[dict[str, Any]]) -> float:
    total = 0.0
    for debt in debts:
        amount = float(debt.get("amount") or 0)
        payments_amount = float(debt.get("payments_amount") or 0)
        total += max(amount - payments_amount, 0.0)
    return total


def _retail_payment_type(payment: dict[str, Any]) -> dict[str, Any]:
    return payment.get("payment_type") or payment.get("type") or {}


def _is_debt_payment_row(payment: dict[str, Any]) -> bool:
    payment_type = _retail_payment_type(payment)
    account = payment_type.get("account") or {}
    haystack = " ".join(
        [
            str(payment_type.get("name") or ""),
            str(account.get("name") or ""),
            str(account.get("code") or ""),
        ]
    ).lower()
    if "debt" in haystack or "qarz" in haystack or "долг" in haystack:
        return True
    if str(account.get("code") or "") == "01001":
        return True
    return bool(payment_type.get("kkm_code") == 2 and not payment_type.get("is_cash"))


def _sum_retail_payment_rows(payments: list[dict[str, Any]], *, debt_only: bool) -> float:
    total = 0.0
    for payment in payments:
        is_debt = _is_debt_payment_row(payment)
        if is_debt != debt_only:
            continue
        total += float(payment.get("value") or 0.0)
    return total


def _retail_payment_type_name(payments: list[dict[str, Any]]) -> str:
    names: list[str] = []
    for payment in payments:
        if _is_debt_payment_row(payment):
            continue
        payment_type = _retail_payment_type(payment)
        name = str(payment_type.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names) or "-"


def _is_debt_service_operation(op: dict[str, Any]) -> bool:
    item = op.get("item") or {}
    haystack = " ".join(
        [
            str(item.get("name") or ""),
            str(item.get("fullname") or ""),
            str(item.get("code") or ""),
        ]
    ).lower()
    item_type = str(item.get("type") or "").lower()
    return ("qarz" in haystack or "долг" in haystack or "debt" in haystack) and item_type == "service"


def _is_real_retail_sale_operation(op: dict[str, Any]) -> bool:
    quantity = _safe_float(op.get("quantity"))
    if abs(quantity) <= 0.000001:
        return False
    return not _is_debt_service_operation(op)


def _has_retail_sale_operations(operations: list[dict[str, Any]]) -> bool:
    return any(_is_real_retail_sale_operation(op) for op in operations)


def _retail_current_debt(customer: dict[str, Any], debts: list[dict[str, Any]]) -> float:
    customer_debt = customer.get("debt")
    if customer_debt is not None:
        return max(_safe_float(customer_debt), 0.0)
    return _sum_retail_open_debts(debts)


async def process_doc_cheque_closed(cheque_uuid: str, *, bot_key: str = "retail") -> None:
    cheque = await regos.get_pos_cheque(cheque_uuid)

    customer = (((cheque.get("card") or {}).get("customer")) or {})
    customer_id = _safe_int(customer.get("id"))
    operating_cash_id = _safe_int(cheque.get("operating_cash_id"))
    session_uuid = str(cheque.get("session_uuid") or cheque.get("session") or "")
    if not operating_cash_id and session_uuid:
        try:
            session = await regos.get_pos_session(session_uuid)
            operating_cash_id = _safe_int(session.get("operating_cash_id"))
            if operating_cash_id:
                cheque["operating_cash_id"] = operating_cash_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("POS/Session/Get ishlamadi. session_uuid=%s error=%s", session_uuid, exc)

    operating_cash: dict[str, Any] | None = None
    if operating_cash_id:
        try:
            operating_cash = await regos.get_operating_cash(operating_cash_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OperatingCash/Get ishlamadi. operating_cash_id=%s error=%s", operating_cash_id, exc)

    debts: list[dict[str, Any]] = []
    if customer_id:
        debts = await regos.get_retail_customer_debts(customer_id)
    total_debt = _retail_current_debt(customer, debts)
    payments = await regos.get_pos_payments(cheque_uuid)
    operations = await regos.get_doc_cheque_operations(cheque_uuid)
    snapshot_key = _retail_customer_snapshot_key(customer)

    if bool(cheque.get("is_return")):
        caption = build_retail_return_caption(cheque=cheque, timezone_name=settings.app_timezone)
        code_part = _safe_filename_part(str(cheque.get("code") or cheque.get("uuid") or "chakana-vozvrat"))
        filename = f"Chakana_Vozvrat_{code_part}.pdf"
        pdf_bytes = render_retail_return_pdf(
            cheque=cheque,
            operations=operations,
            total_debt=total_debt,
            operating_cash=operating_cash,
            timezone_name=settings.app_timezone,
        )

        _, config, _ = _get_telegram_client(bot_key)
        if config.enabled and config.group_configured:
            await _send_bundle(
                bot_key,
                config.group_chat_id,
                pdf_bytes=pdf_bytes,
                caption=caption,
                filename=filename,
            )
        else:
            logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)

        await _send_to_customer_if_mapped(
            bot_key,
            customer,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
        if snapshot_key:
            storage.set_debt_snapshot(snapshot_key, total_debt)
        return

    paid_amount = max(_sum_retail_payment_rows(payments, debt_only=False), 0.0)
    current_sale_debt = max(_sum_retail_payment_rows(payments, debt_only=True), 0.0)
    has_sale_operations = _has_retail_sale_operations(operations)
    is_debt_payment = bool(cheque.get("debt_payment")) or not has_sale_operations

    if is_debt_payment:
        payment_type_name = _retail_payment_type_name(payments)
        payment_amount = paid_amount or float(cheque.get("amount") or 0.0)
        previous_debt = total_debt + payment_amount
        current_debt = total_debt
        if snapshot_key:
            previous_snapshot = storage.get_debt_snapshot(snapshot_key)
            if previous_snapshot is not None and previous_snapshot >= payment_amount:
                previous_debt = previous_snapshot
                current_debt = max(previous_snapshot - payment_amount, 0.0)

        caption = build_retail_payment_caption(cheque=cheque, timezone_name=settings.app_timezone)
        code_part = _safe_filename_part(str(cheque.get("code") or cheque.get("uuid") or "chakana-tolov"))
        filename = f"Chakana_Tolov_{code_part}.pdf"
        pdf_bytes = render_retail_payment_pdf(
            cheque=cheque,
            previous_debt=previous_debt,
            current_debt=current_debt,
            payment_type_name=payment_type_name,
            operating_cash=operating_cash,
            timezone_name=settings.app_timezone,
        )

        _, config, _ = _get_telegram_client(bot_key)
        if config.enabled and config.group_configured:
            await _send_bundle(
                bot_key,
                config.group_chat_id,
                pdf_bytes=pdf_bytes,
                caption=caption,
                filename=filename,
            )
        else:
            logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)

        await _send_to_customer_if_mapped(
            bot_key,
            customer,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
        if snapshot_key:
            storage.set_debt_snapshot(snapshot_key, current_debt)
        return

    amount = float(cheque.get("amount") or 0)
    if current_sale_debt <= 0:
        current_sale_debt = max(amount - paid_amount, 0.0)
    previous_debt = max(total_debt - current_sale_debt, 0.0)
    caption = build_retail_sale_caption(
        cheque=cheque,
        total_debt=total_debt,
        timezone_name=settings.app_timezone,
    )
    code_part = _safe_filename_part(str(cheque.get("code") or cheque.get("uuid") or "chakana-chek"))
    filename = f"Chakana_Chek_{code_part}.pdf"
    pdf_bytes = render_retail_sale_pdf(
        cheque=cheque,
        operations=operations,
        previous_debt=previous_debt,
        paid_amount=paid_amount,
        current_sale_debt=current_sale_debt,
        total_debt=total_debt,
        operating_cash=operating_cash,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if config.enabled and config.group_configured:
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)

    await _send_to_customer_if_mapped(
        bot_key,
        customer,
        pdf_bytes=pdf_bytes,
        caption=caption,
        filename=filename,
    )
    if snapshot_key:
        storage.set_debt_snapshot(snapshot_key, total_debt)


async def process_doc_session_event(
    session_uuid: str,
    *,
    opened: bool,
    bot_key: str = "retail",
) -> None:
    try:
        session = await regos.get_pos_session(session_uuid)
    except RegosApiError as exc:
        logger.warning("POS/Session/Get ishlamadi. session_uuid=%s error=%s", session_uuid, exc)
        return
    operating_cash: dict[str, Any] | None = None
    operating_cash_id = _safe_int(session.get("operating_cash_id"))
    if operating_cash_id:
        try:
            operating_cash = await regos.get_operating_cash(operating_cash_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OperatingCash/Get ishlamadi. operating_cash_id=%s error=%s", operating_cash_id, exc)

    caption = build_session_caption(
        session=session,
        operating_cash=operating_cash,
        opened=opened,
        timezone_name=settings.app_timezone,
    )
    prefix = "SmenaOchildi" if opened else "SmenaYopildi"
    code_part = _safe_filename_part(str(session.get("code") or session.get("uuid") or prefix))
    filename = f"{prefix}_{code_part}.pdf"
    pdf_bytes = render_session_pdf(
        session=session,
        operating_cash=operating_cash,
        opened=opened,
        timezone_name=settings.app_timezone,
    )

    _, config, _ = _get_telegram_client(bot_key)
    if config.enabled and config.group_configured:
        await _send_bundle(
            bot_key,
            config.group_chat_id,
            pdf_bytes=pdf_bytes,
            caption=caption,
            filename=filename,
        )
    else:
        logger.info("Telegram group hali sozlanmagan. bot=%s", bot_key)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/regos/webhook")
async def regos_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    debug_path = settings.storage_path.parent / "last_regos_webhook.json"
    archive_dir = settings.storage_path.parent / "webhook_archive"
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    archive_name = datetime.now().strftime("%Y%m%d-%H%M%S-%f.json")
    (archive_dir / archive_name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    action = payload.get("action")
    if action != "HandleWebhook":
        return {"ok": True, "ignored": "unknown_root_action"}

    incoming_integration_id = str(payload.get("connected_integration_id") or "")
    logger.info(
        "Webhook qabul qilindi. event_id=%s action=%s connected_integration_id=%s",
        payload.get("event_id"),
        ((payload.get("data") or {}).get("action") or ""),
        incoming_integration_id,
    )
    if settings.regos_connected_integration_id.strip():
        if incoming_integration_id != settings.regos_connected_integration_id:
            raise HTTPException(status_code=401, detail="connected_integration_id mos emas")

    event_id = str(payload.get("event_id") or "")
    if not event_id:
        raise HTTPException(status_code=400, detail="event_id topilmadi")

    data = payload.get("data") or {}
    event_action = str(data.get("action") or "")
    event_data = data.get("data") or {}
    object_id = _safe_int(event_data.get("id"))
    object_uuid = str(event_data.get("uuid") or "")

    if not event_action:
        return {"ok": True, "ignored": "missing_event_action"}

    started = storage.try_start_event(event_id, event_action)
    if not started:
        status = storage.get_event_status(event_id)
        return {"ok": True, "duplicate": True, "status": status}

    try:
        event_bot_key = EVENT_BOT_PREFERENCES.get(event_action, "shared")

        if event_action == "DocWholeSalePerformed":
            if not object_id:
                raise RuntimeError("DocWholeSalePerformed eventida id yo'q")
            await process_wholesale_performed(object_id, bot_key=event_bot_key)
        elif event_action == "DocPaymentPerformed":
            if not object_id:
                raise RuntimeError("DocPaymentPerformed eventida id yo'q")
            await process_payment_performed(object_id, bot_key=event_bot_key)
        elif event_action == "DocWholeSaleReturnPerformed":
            if not object_id:
                raise RuntimeError("DocWholeSaleReturnPerformed eventida id yo'q")
            await process_wholesale_return_performed(object_id, bot_key=event_bot_key)
        elif event_action == "DocOrderFromPartnerAdded":
            if not object_id:
                raise RuntimeError("DocOrderFromPartnerAdded eventida id yo'q")
            await process_order_from_partner_added(object_id, bot_key=event_bot_key)
        elif event_action == "DocPurchasePerformed":
            if not object_id:
                raise RuntimeError("DocPurchasePerformed eventida id yo'q")
            await process_purchase_performed(object_id, bot_key=event_bot_key)
        elif event_action == "DocReturnsToPartnerPerformed":
            if not object_id:
                raise RuntimeError("DocReturnsToPartnerPerformed eventida id yo'q")
            await process_returns_to_partner_performed(object_id, bot_key=event_bot_key)
        elif event_action == "DocMovementPerformed":
            if not object_id:
                raise RuntimeError("DocMovementPerformed eventida id yo'q")
            await process_movement_performed(object_id, bot_key=event_bot_key)
        elif event_action == "DocChequeClosed":
            if not object_uuid:
                raise RuntimeError("DocChequeClosed eventida uuid yo'q")
            await process_doc_cheque_closed(object_uuid, bot_key=event_bot_key)
        elif event_action == "DocSessionOpened":
            if not object_uuid:
                raise RuntimeError("DocSessionOpened eventida uuid yo'q")
            await process_doc_session_event(object_uuid, opened=True, bot_key=event_bot_key)
        elif event_action == "DocSessionClosed":
            if not object_uuid:
                raise RuntimeError("DocSessionClosed eventida uuid yo'q")
            await process_doc_session_event(object_uuid, opened=False, bot_key=event_bot_key)
        else:
            logger.info("Webhook e'tiborsiz qoldirildi: %s", event_action)

        storage.mark_processed(event_id, event_action)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        storage.release_event(event_id)
        logger.exception("Webhook qayta ishlashda xato. event_id=%s", event_id)
        raise HTTPException(status_code=500, detail=f"processing_failed: {exc}") from exc


async def _handle_telegram_update(
    configured_bot: TelegramBotConfig,
    payload: dict[str, Any],
) -> dict[str, bool]:
    message = payload.get("message") or {}
    if not message:
        return {"ok": True}

    chat_id = (message.get("chat") or {}).get("id")
    if not chat_id:
        return {"ok": True}

    text = str(message.get("text") or "").strip()
    contact = message.get("contact")
    is_private_chat = _is_private_chat(message)
    bot_key = configured_bot.key

    if not is_private_chat and not _is_allowed_group_chat(bot_key, chat_id):
        logger.info("Unauthorized group ignored. bot=%s chat_id=%s", bot_key, chat_id)
        return {"ok": True}

    if text.startswith("/start"):
        if not is_private_chat:
            await _send_message(
                bot_key,
                chat_id,
                "Telefon raqamini bog'lash uchun botga shaxsiy yozing va /start yuboring.",
            )
            return {"ok": True}

        reply_markup = {
            "keyboard": [[{"text": "Telefon raqamni ulashish", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
        await _send_message(
            bot_key,
            chat_id,
            "Assalomu alaykum. Xabarlarni olish uchun telefon raqamingizni ulashing.",
            reply_markup=reply_markup,
        )
        return {"ok": True}

    if contact:
        if not is_private_chat:
            await _send_message(
                bot_key,
                chat_id,
                "Telefon raqamini faqat bot bilan shaxsiy chatda ulashing.",
            )
            return {"ok": True}

        from_user = message.get("from") or {}
        contact_user_id = contact.get("user_id")
        from_user_id = from_user.get("id")
        if contact_user_id and from_user_id and int(contact_user_id) != int(from_user_id):
            await _send_message(
                bot_key,
                chat_id,
                "O'zingizning telefon raqamingizni yuboring.",
                reply_markup={"remove_keyboard": True},
            )
            return {"ok": True}

        phone = normalize_phone(str(contact.get("phone_number") or ""))
        if not phone:
            await _send_message(bot_key, chat_id, "Telefon raqamni o'qib bo'lmadi. Qayta yuboring.")
            return {"ok": True}

        first_name = str(contact.get("first_name") or "")
        last_name = str(contact.get("last_name") or "")
        full_name = (f"{first_name} {last_name}").strip() or "Mijoz"
        storage.upsert_phone_link(bot_key, phone, int(chat_id), full_name)
        await _send_message(
            bot_key,
            chat_id,
            "Telefon saqlandi.",
            reply_markup={"remove_keyboard": True},
        )
        return {"ok": True}

    if text.startswith("/myphone"):
        await _send_message(bot_key, chat_id, "Telefonni ulashish uchun /start buyrug'ini yuboring.")
        return {"ok": True}

    if is_private_chat and text:
        existing_link = storage.get_phone_link_by_chat_id(bot_key, int(chat_id))
        if existing_link is None:
            reply_markup = {
                "keyboard": [[{"text": "Telefon raqamni ulashish", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            }
            await _send_message(
                bot_key,
                chat_id,
                "Telefoningiz hali ulanmagan. Davom etish uchun raqamingizni ulashing.",
                reply_markup=reply_markup,
            )
            return {"ok": True}

    return {"ok": True}


@app.post("/telegram/webhook/{bot_key}/{secret}")
async def telegram_webhook_v2(bot_key: str, secret: str, request: Request) -> dict[str, bool]:
    configured_bot = _resolve_registered_bot_config(bot_key)
    if secret != configured_bot.webhook_secret:
        raise HTTPException(status_code=404, detail="Not found")
    payload = await request.json()
    return await _handle_telegram_update(configured_bot, payload)


@app.post("/telegram/webhook/{secret}")
async def telegram_webhook_legacy(secret: str, request: Request) -> dict[str, bool]:
    configured_bot = settings.shared_bot_config()
    if not configured_bot.enabled or secret != configured_bot.webhook_secret:
        raise HTTPException(status_code=404, detail="Not found")
    payload = await request.json()
    return await _handle_telegram_update(configured_bot, payload)
