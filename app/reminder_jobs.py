from __future__ import annotations

import argparse
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.formatting import extract_first_phone, format_money, normalize_phone, unix_to_local
from app.regos_client import RegosClient
from app.rendering import (
    render_debt_report_pdf,
    render_inventory_snapshot_pdf,
    render_low_stock_pdf,
    render_private_debt_pdf,
)
from app.storage import Storage
from app.telegram_client import TelegramClient

logger = logging.getLogger("reminder-bot")
ALLOWED_PARTNER_GROUPS = {"поставщики", "покупатели"}


@dataclass
class DebtRecord:
    source: str
    name: str
    phone: str
    amount: float


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


def _format_qty(value: float) -> str:
    rounded = round(float(value or 0), 3)
    if abs(rounded - int(rounded)) < 0.001:
        return str(int(round(rounded)))
    return f"{rounded:g}"


def _format_currency_label(amount: float, currency_code: str) -> str:
    rounded = round(float(amount or 0), 2)
    if abs(rounded - int(rounded)) < 0.005:
        value = f"{int(round(rounded)):,}".replace(",", " ")
    else:
        value = f"{rounded:,.2f}".replace(",", " ")
    return f"{currency_code} {value}"


def _phone_from_entity(entity: dict[str, Any]) -> str:
    return normalize_phone(extract_first_phone(str(entity.get("main_phone") or entity.get("phones") or "")))


class ReminderRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = Storage(self.settings.storage_path)
        self.regos = RegosClient(
            base_url=self.settings.regos_base_url,
            integration_key=self.settings.regos_integration_key,
            timeout_seconds=self.settings.regos_timeout_seconds,
            use_oauth=self.settings.regos_use_oauth,
            token_url=self.settings.regos_token_url,
            client_id=self.settings.regos_client_id,
            client_secret=self.settings.regos_client_secret,
            oauth_scope=self.settings.regos_oauth_scope,
        )
        self.group_bot_config = self.settings.bot_config("reminder")
        self.group_client = TelegramClient(self.group_bot_config.bot_token) if self.group_bot_config.enabled else None
        self.private_bot_config = self.settings.shared_bot_config()
        self.private_client = (
            TelegramClient(self.private_bot_config.bot_token) if self.private_bot_config.enabled else None
        )
        self._usd_rate: float | None = None

    async def run_morning(self) -> None:
        if not self._can_send_group():
            logger.info("Reminder bot hali to'liq sozlanmagan, morning report o'tkazib yuborildi.")
            return
        usd_rate = await self._get_usd_rate()
        grouped = await self._fetch_inventory(zero_quantity=False)
        low_grouped = await self._fetch_inventory(zero_quantity=True)
        summary_rows, total_item_count, total_units, total_value = self._build_inventory_summary(
            grouped,
            usd_rate=usd_rate,
        )
        report_date = unix_to_local(int(time.time()), self.settings.app_timezone)

        full_caption = self._build_inventory_caption(summary_rows, total_value)
        await self.group_client.send_document_bytes(
            self.group_bot_config.group_chat_id,
            render_inventory_snapshot_pdf(
                report_date=report_date,
                stock_rows=summary_rows,
                total_item_count=total_item_count,
                total_units=total_units,
                total_value=total_value,
                currency_code="USD",
            ),
            filename="Ombor_Qoldiq_Hisoboti.pdf",
            caption=full_caption,
        )

        low_text, low_count = self._build_low_stock_text(low_grouped)
        if low_count == 0:
            await self.group_client.send_message(
                self.group_bot_config.group_chat_id,
                "Kam qolgan mahsulotlar hisoboti\n\nBugun 1 ta va undan kam qolgan mahsulot topilmadi.",
            )
        else:
            await self.group_client.send_document_bytes(
                self.group_bot_config.group_chat_id,
                render_low_stock_pdf(
                    report_date=report_date,
                    rows=low_text,
                ),
                filename="Kam_Qolgan_Mahsulotlar.pdf",
                caption=f"Kam qolgan mahsulotlar\n\n1 ta va undan kam qolgan mahsulotlar: {low_count} ta",
            )

    async def run_debts(self) -> None:
        if not self._can_send_group():
            logger.info("Reminder bot hali to'liq sozlanmagan, debt report o'tkazib yuborildi.")
            return

        records = await self._collect_debt_records()
        report_date = unix_to_local(int(time.time()), self.settings.app_timezone)

        if records:
            await self.group_client.send_document_bytes(
                self.group_bot_config.group_chat_id,
                render_debt_report_pdf(
                    report_date=report_date,
                    records=[
                        {
                            "source": row.source,
                            "name": row.name,
                            "phone": row.phone,
                            "amount": row.amount,
                        }
                        for row in records
                    ],
                    total_amount=sum(row.amount for row in records),
                ),
                filename="Qarzdorlar_Royxati.pdf",
                caption=self._build_debt_group_caption(records),
            )
        else:
            await self.group_client.send_message(
                self.group_bot_config.group_chat_id,
                "Qarzdorlar ro'yxati\n\nBugun qarzdorlar topilmadi.",
            )

        await self._send_private_reminders(records)

    def _can_send_group(self) -> bool:
        return bool(self.group_client and self.group_bot_config.group_configured)

    async def _fetch_inventory(self, *, zero_quantity: bool) -> dict[int, dict[str, Any]]:
        stocks = await self._fetch_all_stocks()
        grouped: dict[int, dict[str, Any]] = {}
        for stock in stocks:
            stock_id = _safe_int(stock.get("id"))
            stock_name = str(stock.get("name") or f"Sklad {stock_id}")
            items = await self._fetch_all_item_ext(stock_id=stock_id, zero_quantity=zero_quantity)
            for row in items:
                item = row.get("item") or {}
                item_id = _safe_int(item.get("id"))
                quantity = _safe_float(((row.get("quantity") or {}).get("allowed")))
                if item_id == 0:
                    continue
                entry = grouped.setdefault(
                    item_id,
                    {
                        "id": item_id,
                        "name": str(item.get("name") or item.get("code") or f"Item {item_id}"),
                        "code": str(item.get("code") or ""),
                        "unit": str(((item.get("unit") or {}).get("name")) or ""),
                        "cost": _safe_float(row.get("last_purchase_cost")) or _safe_float(row.get("price")),
                        "stocks": {},
                        "total": 0.0,
                    },
                )
                entry["stocks"][stock_name] = quantity
                entry["total"] += quantity
        return grouped

    async def _fetch_all_stocks(self) -> list[dict[str, Any]]:
        offset = 0
        result: list[dict[str, Any]] = []
        while True:
            body = await self.regos.get_stocks(limit=1000, offset=offset)
            rows = body.get("result", [])
            result.extend(rows)
            next_offset = _safe_int(body.get("next_offset"))
            total = _safe_int(body.get("total"))
            if not next_offset or next_offset == offset or len(result) >= total:
                break
            offset = next_offset
        return result

    async def _fetch_all_item_ext(self, *, stock_id: int, zero_quantity: bool) -> list[dict[str, Any]]:
        offset = 0
        result: list[dict[str, Any]] = []
        while True:
            body = await self.regos.get_item_ext(
                stock_id=stock_id,
                limit=1000,
                offset=offset,
                zero_quantity=zero_quantity,
            )
            rows = body.get("result", [])
            result.extend(rows)
            next_offset = _safe_int(body.get("next_offset"))
            total = _safe_int(body.get("total"))
            if not next_offset or next_offset == offset or len(result) >= total:
                break
            offset = next_offset
        return result

    async def _fetch_all_partners(self) -> list[dict[str, Any]]:
        offset = 0
        result: list[dict[str, Any]] = []
        while True:
            body = await self.regos.get_partners(limit=1000, offset=offset)
            rows = body.get("result", [])
            result.extend(rows)
            next_offset = _safe_int(body.get("next_offset"))
            total = _safe_int(body.get("total"))
            if not next_offset or next_offset == offset or len(result) >= total:
                break
            offset = next_offset
        return result

    async def _fetch_all_retail_customers(self) -> list[dict[str, Any]]:
        offset = 0
        result: list[dict[str, Any]] = []
        while True:
            body = await self.regos.get_retail_customers(limit=1000, offset=offset)
            rows = body.get("result", [])
            result.extend(rows)
            next_offset = _safe_int(body.get("next_offset"))
            total = _safe_int(body.get("total"))
            if not next_offset or next_offset == offset or len(result) >= total:
                break
            offset = next_offset
        return result

    def _build_inventory_summary(
        self,
        grouped: dict[int, dict[str, Any]],
        *,
        usd_rate: float,
    ) -> tuple[list[dict[str, Any]], int, float, float]:
        by_stock: dict[str, dict[str, float | int | str]] = {}
        total_units = 0.0
        total_value = 0.0
        total_item_count = len(grouped)

        for item in grouped.values():
            item_cost = _safe_float(item.get("cost"))
            for stock_name, quantity_raw in item["stocks"].items():
                quantity = _safe_float(quantity_raw)
                if quantity <= 0:
                    continue
                entry = by_stock.setdefault(
                    stock_name,
                    {"name": stock_name, "item_count": 0, "unit_total": 0.0, "value_total": 0.0},
                )
                value_usd = self._convert_base_to_usd(quantity * item_cost, usd_rate)
                entry["item_count"] = int(entry["item_count"]) + 1
                entry["unit_total"] = float(entry["unit_total"]) + quantity
                entry["value_total"] = float(entry["value_total"]) + value_usd
                total_units += quantity
                total_value += value_usd

        rows = sorted(by_stock.values(), key=lambda row: str(row["name"]).lower())
        return rows, total_item_count, total_units, total_value

    def _build_inventory_caption(self, stock_rows: list[dict[str, Any]], total_value: float) -> str:
        warehouse_count = len(stock_rows)
        return "\n".join(
            [
                "Ertalabgi ombor qoldiq hisoboti",
                f"Omborlar: {warehouse_count} ta",
                f"Qoldiq summasi: {_format_currency_label(total_value, 'USD')}",
            ]
        )

    def _build_low_stock_text(self, grouped: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        rows = [item for item in grouped.values() if item["total"] <= 1]
        rows.sort(key=lambda x: (x["total"], x["name"].lower()))
        prepared: list[dict[str, Any]] = []
        for item in rows:
            stock_parts = [f"{name}: {_format_qty(qty)}" for name, qty in sorted(item["stocks"].items()) if _safe_float(qty) > 0]
            prepared.append(
                {
                    "name": str(item["name"]),
                    "stocks_text": ", ".join(stock_parts) if stock_parts else "-",
                    "total": _format_qty(item["total"]),
                }
            )
        return prepared, len(prepared)

    async def _collect_debt_records(self) -> list[DebtRecord]:
        usd_rate = await self._get_usd_rate()
        partner_records = await self._collect_partner_debts(usd_rate=usd_rate)
        retail_records = await self._collect_retail_debts(usd_rate=usd_rate)
        return sorted(partner_records + retail_records, key=lambda x: x.amount, reverse=True)

    async def _collect_partner_debts(self, *, usd_rate: float) -> list[DebtRecord]:
        partners = await self._fetch_all_partners()
        semaphore = asyncio.Semaphore(10)

        async def load(partner: dict[str, Any]) -> DebtRecord | None:
            name = str(partner.get("name") or "").strip()
            if not name or name.lower() == "qoldiq":
                return None
            group_name = str(((partner.get("group") or {}).get("name")) or "").strip().lower()
            if group_name not in ALLOWED_PARTNER_GROUPS:
                return None
            async with semaphore:
                amount_base = await self.regos.get_partner_current_balance(_safe_int(partner.get("id")))
            amount = self._convert_base_to_usd(amount_base, usd_rate)
            if amount <= 0:
                return None
            return DebtRecord(
                source="Ulgurji",
                name=name,
                phone=_phone_from_entity(partner),
                amount=amount,
            )

        tasks = [load(partner) for partner in partners]
        results = await asyncio.gather(*tasks)
        return [item for item in results if item is not None]

    async def _collect_retail_debts(self, *, usd_rate: float) -> list[DebtRecord]:
        customers = await self._fetch_all_retail_customers()
        results: list[DebtRecord] = []
        for customer in customers:
            amount = self._convert_base_to_usd(_safe_float(customer.get("debt")), usd_rate)
            if amount <= 0:
                continue
            results.append(
                DebtRecord(
                    source="Chakana",
                    name=str(customer.get("full_name") or customer.get("first_name") or "Noma'lum").strip(),
                    phone=_phone_from_entity(customer),
                    amount=amount,
                )
            )
        return results

    def _build_debt_group_caption(self, records: list[DebtRecord]) -> str:
        wholesale_count = sum(1 for row in records if row.source == "Ulgurji")
        retail_count = sum(1 for row in records if row.source == "Chakana")
        total = sum(row.amount for row in records)

        return "\n".join(
            [
                "Qarzdorlar ro'yxati",
                f"Ulgurji: {wholesale_count} ta",
                f"Chakana: {retail_count} ta",
                f"Jami qarz: {_format_currency_label(total, 'USD')}",
            ]
        )

    async def _send_private_reminders(self, records: list[DebtRecord]) -> None:
        if not self.private_client or not records:
            return

        by_phone: dict[str, list[DebtRecord]] = defaultdict(list)
        for row in records:
            if row.phone:
                by_phone[row.phone].append(row)

        for phone, rows in by_phone.items():
            chat_id = self.storage.get_chat_id_by_phone("shared", phone)
            if not chat_id:
                continue
            total = sum(row.amount for row in rows)
            debtor_name = rows[0].name if rows else "Noma'lum"
            report_date = unix_to_local(int(time.time()), self.settings.app_timezone)
            pdf_bytes = render_private_debt_pdf(
                report_date=report_date,
                debtor_name=debtor_name,
                debtor_phone=phone,
                records=[
                    {
                        "source": row.source,
                        "amount": row.amount,
                    }
                    for row in rows
                ],
                total_amount=total,
            )
            await self.private_client.send_document_bytes(
                chat_id,
                pdf_bytes,
                filename="Qarzdorlik_Eslatmasi.pdf",
                caption="\n".join(
                    [
                        f"Assalomu alaykum, {debtor_name}.",
                        "Sizda qarzdorlik mavjudligini eslatamiz.",
                        f"Jami: {_format_currency_label(total, 'USD')}",
                        "Iltimos, to'lovni imkon qadar vaqtida amalga oshiring.",
                    ]
                ),
            )

    async def _get_usd_rate(self) -> float:
        if self._usd_rate and self._usd_rate > 0:
            return self._usd_rate

        body = await self.regos.get_currencies(search="USD", limit=100, offset=0)
        rows = body.get("result", [])
        for row in rows:
            code = str(row.get("code_chr") or "").upper()
            if code != "USD":
                continue
            rate = _safe_float(row.get("exchange_rate"))
            if rate > 0:
                self._usd_rate = rate
                return rate

        logger.warning("USD kursi topilmadi, fallback rate=1 ishlatildi.")
        self._usd_rate = 1.0
        return self._usd_rate

    @staticmethod
    def _convert_base_to_usd(amount: float, usd_rate: float) -> float:
        if usd_rate <= 0:
            return float(amount or 0)
        return float(amount or 0) / usd_rate


async def _run(mode: str) -> None:
    runner = ReminderRunner()
    if mode == "morning":
        await runner.run_morning()
    elif mode == "debts":
        await runner.run_debts()
    elif mode == "all":
        await runner.run_morning()
        await runner.run_debts()
    else:
        raise SystemExit(f"Unknown mode: {mode}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["morning", "debts", "all"], required=True)
    args = parser.parse_args()
    asyncio.run(_run(args.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
