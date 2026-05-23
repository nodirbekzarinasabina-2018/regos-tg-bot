from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

from app.main import regos
from app.message_builders import resolve_wholesale_sale_amount


def ts_to_iso(value: object) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("doc_id", type=int)
    args = parser.parse_args()

    doc = await regos.get_doc_wholesale(args.doc_id)
    operations = await regos.get_wholesale_operations(args.doc_id)

    partner = doc.get("partner") or {}
    firm = doc.get("firm") or {}
    partner_id = int(partner.get("id") or 0)
    firm_id = int(firm.get("id") or 0)
    current_balance = 0.0
    if partner_id:
        current_balance = await regos.get_partner_current_balance(partner_id, firm_id or None)

    operation_rows = []
    operations_total = 0.0
    for index, op in enumerate(operations, start=1):
        item = op.get("item") or {}
        quantity = float(op.get("quantity") or 0)
        price = float(op.get("price") or 0)
        row_total = quantity * price
        operations_total += row_total
        operation_rows.append(
            {
                "index": index,
                "item": item.get("name") or item.get("code") or f"Item-{item.get('id', '-')}",
                "quantity": quantity,
                "price": price,
                "row_total": row_total,
            }
        )

    payload = {
        "doc_id": args.doc_id,
        "doc_code": doc.get("code"),
        "doc_date_utc": ts_to_iso(doc.get("date")),
        "doc_amount": doc.get("amount"),
        "doc_currency": doc.get("currency"),
        "doc_exchange_rate": doc.get("exchange_rate"),
        "partner": {
            "id": partner.get("id"),
            "name": partner.get("name") or partner.get("full_name"),
            "main_phone": partner.get("main_phone"),
            "phones": partner.get("phones"),
        },
        "firm": {
            "id": firm.get("id"),
            "name": firm.get("name"),
        },
        "current_balance_base": current_balance,
        "resolved_sale_amount": resolve_wholesale_sale_amount(doc, operations),
        "operations_total": operations_total,
        "operations_count": len(operations),
        "operations": operation_rows,
        "raw_doc": doc,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
