from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.main import process_payment_performed, process_wholesale_performed, regos, storage


def _ts_to_dt(value: object) -> datetime | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


async def _fetch_by_range(method: str, start_id: int, end_id: int, step: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for chunk_start in range(start_id, end_id + 1, step):
        chunk_end = min(chunk_start + step - 1, end_id)
        ids = list(range(chunk_start, chunk_end + 1))
        body = await regos._post(method, {"ids": ids, "limit": len(ids), "offset": 0})  # noqa: SLF001
        found.extend(body.get("result", []))
    return found


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument("--sale-start", type=int, default=10600)
    parser.add_argument("--sale-end", type=int, default=13000)
    parser.add_argument("--payment-start", type=int, default=11200)
    parser.add_argument("--payment-end", type=int, default=14000)
    parser.add_argument("--step", type=int, default=250)
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    sales = await _fetch_by_range("DocWholeSale/Get", args.sale_start, args.sale_end, args.step)
    payments = await _fetch_by_range("DocPayment/Get", args.payment_start, args.payment_end, args.step)

    recent_sales = [
        item for item in sales
        if (_ts_to_dt(item.get("date")) or datetime.min.replace(tzinfo=timezone.utc)) >= since
    ]
    recent_payments = [
        item for item in payments
        if (_ts_to_dt(item.get("date")) or datetime.min.replace(tzinfo=timezone.utc)) >= since
    ]

    recent_sales.sort(key=lambda item: int(item.get("id") or 0))
    recent_payments.sort(key=lambda item: int(item.get("id") or 0))

    replayed_sales: list[int] = []
    replayed_payments: list[int] = []

    for item in recent_sales:
        doc_id = int(item.get("id") or 0)
        if not doc_id or storage.is_document_processed("DocWholeSalePerformed", doc_id):
            continue
        await process_wholesale_performed(doc_id, bot_key="wholesale")
        replayed_sales.append(doc_id)

    for item in recent_payments:
        doc_id = int(item.get("id") or 0)
        if not doc_id or storage.is_document_processed("DocPaymentPerformed", doc_id):
            continue
        await process_payment_performed(doc_id, bot_key="wholesale")
        replayed_payments.append(doc_id)

    print(
        json.dumps(
            {
                "since_utc": since.isoformat(),
                "recent_sale_ids": [int(item.get("id") or 0) for item in recent_sales],
                "recent_payment_ids": [int(item.get("id") or 0) for item in recent_payments],
                "replayed_sales": replayed_sales,
                "replayed_payments": replayed_payments,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
