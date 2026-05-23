from __future__ import annotations

from typing import Any

from app.formatting import extract_first_phone, format_money, normalize_phone, unix_to_local


def _person_name(person: dict[str, Any] | None) -> str:
    if not person:
        return ""

    direct_name = person.get("full_name") or person.get("fullname") or person.get("name")
    if direct_name:
        return str(direct_name).strip()

    parts = [
        str(person.get("first_name") or "").strip(),
        str(person.get("last_name") or "").strip(),
        str(person.get("middle_name") or "").strip(),
    ]
    combined = " ".join(part for part in parts if part)
    return combined.strip()


def _customer_name(customer: dict[str, Any] | None) -> str:
    return _person_name(customer) or "Noma'lum"


def _stock_name(stock: dict[str, Any] | None) -> str:
    if not stock:
        return "-"
    return str(stock.get("name") or stock.get("fullname") or stock.get("code") or "-")


def _format_amount_text(amount: float) -> str:
    if abs(amount - int(amount)) > 0.001:
        return f"{amount:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
    return format_money(amount)


def _format_quantity(quantity: float) -> str:
    if abs(quantity - int(quantity)) < 0.001:
        return str(int(quantity))
    return f"{quantity:,.3f}".replace(",", " ").rstrip("0").rstrip(".")


def _item_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("code") or f"Item-{item.get('id', '-')}")


def _normalize_display_phone(value: str) -> str:
    phone = normalize_phone(extract_first_phone(str(value or "")))
    return phone or "-"


def _append_support_lines(
    lines: list[str],
    *,
    support_phones: list[str] | None = None,
    support_telegram: str | None = None,
) -> None:
    phones = [phone for phone in (support_phones or []) if phone]
    if not phones and not support_telegram:
        return

    lines.append("")
    if phones:
        lines.append(f"Murojaat uchun: {', '.join(phones)}")
    if support_telegram:
        lines.append(f"Telegram: {support_telegram}")


def build_sale_message(
    *,
    doc: dict[str, Any],
    operations: list[dict[str, Any]],
    total_debt: float,
    timezone_name: str,
    support_phones: list[str] | None = None,
    support_telegram: str | None = None,
    max_items: int = 15,
) -> str:
    code = doc.get("code") or f"ID-{doc.get('id', '-')}"
    date_text = unix_to_local(int(doc.get("date") or 0), timezone_name)
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("full_name") or "Noma'lum"
    partner_phone = _normalize_display_phone(partner.get("main_phone") or partner.get("phones") or "")
    actor = _person_name(doc.get("attached_user")) or _person_name(doc.get("seller")) or "Noma'lum"
    amount = float(doc.get("amount") or 0)

    lines = [
        "XARID QILINDI",
        "",
        str(code),
        date_text,
        partner_name,
        partner_phone,
        f"Amalni bajargan: {actor}",
        "",
        "Mahsulotlar:",
    ]

    if operations:
        visible_operations = operations[:max_items]
        for idx, op in enumerate(visible_operations, start=1):
            item = op.get("item") or {}
            item_name = _item_name(item)
            quantity = float(op.get("quantity") or 0)
            price = float(op.get("price") or 0)
            row_total = quantity * price
            lines.append(
                f"{idx}) {item_name} {_format_quantity(quantity)} x {format_money(price)} = {format_money(row_total)}"
            )

        remaining_count = len(operations) - len(visible_operations)
        if remaining_count > 0:
            lines.append(f"... yana {remaining_count} ta mahsulot")
    else:
        lines.append("1) Pozitsiyalar topilmadi")

    lines.extend(
        [
            "",
            f"Jami: {format_money(amount)}",
            f"Umumiy qarz: {format_money(total_debt)}",
        ]
    )
    _append_support_lines(
        lines,
        support_phones=support_phones,
        support_telegram=support_telegram,
    )
    return "\n".join(lines)


def build_sale_caption(*, doc: dict[str, Any], timezone_name: str) -> str:
    code = doc.get("code") or f"ID-{doc.get('id', '-')}"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("full_name") or "Noma'lum"
    date_text = unix_to_local(int(doc.get("date") or 0), timezone_name).replace(" ", ", ")
    currency = doc.get("currency") or {}
    currency_code = str(currency.get("code_chr") or "UZS")
    amount = float(doc.get("amount") or 0)

    return "\n".join(
        [
            f"Yangi savdo #{code}",
            f"Mijoz: {partner_name}",
            f"Sana: {date_text}",
            f"Jami: {_format_amount_text(amount)} {currency_code}",
        ]
    )


def build_payment_message(
    *,
    payment_doc: dict[str, Any],
    prev_debt: float,
    current_debt: float,
    timezone_name: str,
) -> str:
    code = payment_doc.get("code") or f"ID-{payment_doc.get('id', '-')}"
    date_text = unix_to_local(int(payment_doc.get("date") or 0), timezone_name)
    partner = payment_doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("full_name") or "Noma'lum"
    partner_phone = _normalize_display_phone(partner.get("main_phone") or partner.get("phones") or "")
    payment_amount = float(payment_doc.get("amount") or 0)

    return "\n".join(
        [
            "TO'LOV QABUL QILINDI",
            "",
            str(code),
            date_text,
            partner_name,
            partner_phone,
            "",
            f"To'lov: {format_money(payment_amount)} so'm",
            f"Oldingi qarz: {format_money(prev_debt)} so'm",
            f"Qolgan qarz: {format_money(current_debt)} so'm",
        ]
    )


def build_payment_caption(*, payment_doc: dict[str, Any], timezone_name: str) -> str:
    code = payment_doc.get("code") or f"ID-{payment_doc.get('id', '-')}"
    partner = payment_doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("full_name") or "Noma'lum"
    date_text = unix_to_local(int(payment_doc.get("date") or 0), timezone_name).replace(" ", ", ")
    payment_type = (payment_doc.get("type") or {}).get("account", {}).get("currency") or {}
    currency_code = str(payment_type.get("code_chr") or "UZS")
    amount = float(payment_doc.get("amount") or 0)

    return "\n".join(
        [
            f"To'lov #{code}",
            f"Mijoz: {partner_name}",
            f"Sana: {date_text}",
            f"To'lov: {_format_amount_text(amount)} {currency_code}",
        ]
    )


def build_retail_return_caption(
    *,
    cheque: dict[str, Any],
    timezone_name: str,
) -> str:
    code = cheque.get("code") or f"ID-{cheque.get('uuid', '-')}"
    customer = ((cheque.get("card") or {}).get("customer") or {})
    customer_name = _customer_name(customer)
    date_text = unix_to_local(int(cheque.get("date") or 0), timezone_name).replace(" ", ", ")
    amount = float(cheque.get("amount") or 0)

    return "\n".join(
        [
            f"Chakana vozvrat #{code}",
            f"Mijoz: {customer_name}",
            f"Sana: {date_text}",
            f"Vozvrat: {format_money(amount)} UZS",
        ]
    )


def build_session_caption(
    *,
    session: dict[str, Any],
    operating_cash: dict[str, Any] | None,
    opened: bool,
    timezone_name: str,
) -> str:
    code = session.get("code") or f"ID-{session.get('uuid', '-')}"
    when_value = session.get("start_date") if opened else session.get("close_date")
    when_text = unix_to_local(int(when_value or 0), timezone_name).replace(" ", ", ")
    title = "Smena ochildi" if opened else "Smena yopildi"
    stock_name = _stock_name((operating_cash or {}).get("stock"))
    cash_number = str((operating_cash or {}).get("id") or session.get("operating_cash_id") or "-")

    return "\n".join(
        [
            f"{title} #{code}",
            f"Kassa: {cash_number}",
            f"Ombor kassasi: {stock_name}",
            f"Sana: {when_text}",
        ]
    )


def build_movement_caption(
    *,
    movement_doc: dict[str, Any],
    operations: list[dict[str, Any]],
    timezone_name: str,
) -> str:
    code = movement_doc.get("code") or f"ID-{movement_doc.get('id', '-')}"
    date_text = unix_to_local(int(movement_doc.get("date") or 0), timezone_name).replace(" ", ", ")
    sender_name = _stock_name(movement_doc.get("stock_sender"))
    receiver_name = _stock_name(movement_doc.get("stock_receiver"))
    total_quantity = sum(float(op.get("quantity") or 0) for op in operations)

    return "\n".join(
        [
            f"Peremisheniya #{code}",
            f"Qayerdan: {sender_name}",
            f"Qayerga: {receiver_name}",
            f"Sana: {date_text}",
            f"Pozitsiya: {len(operations)} ta | Soni: {_format_quantity(total_quantity)}",
        ]
    )


def build_purchase_caption(
    *,
    doc: dict[str, Any],
    timezone_name: str,
) -> str:
    code = doc.get("code") or f"ID-{doc.get('id', '-')}"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("full_name") or "Noma'lum"
    stock_name = _stock_name(doc.get("stock"))
    date_text = unix_to_local(int(doc.get("date") or 0), timezone_name).replace(" ", ", ")
    amount = float(doc.get("amount") or 0)

    return "\n".join(
        [
            f"Postupleniya #{code}",
            f"Kontragent: {partner_name}",
            f"Sklad: {stock_name}",
            f"Sana: {date_text}",
            f"Jami: {format_money(amount)} UZS",
        ]
    )


def build_returns_to_partner_caption(
    *,
    doc: dict[str, Any],
    timezone_name: str,
) -> str:
    code = doc.get("code") or f"ID-{doc.get('id', '-')}"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("full_name") or "Noma'lum"
    stock_name = _stock_name(doc.get("stock"))
    date_text = unix_to_local(int(doc.get("date") or 0), timezone_name).replace(" ", ", ")
    amount = float(doc.get("amount") or 0)

    return "\n".join(
        [
            f"Vozvrat kontragentga #{code}",
            f"Kontragent: {partner_name}",
            f"Sklad: {stock_name}",
            f"Sana: {date_text}",
            f"Jami: {format_money(amount)} UZS",
        ]
    )


def build_wholesale_return_caption(
    *,
    doc: dict[str, Any],
    timezone_name: str,
) -> str:
    code = doc.get("code") or f"ID-{doc.get('id', '-')}"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("full_name") or "Noma'lum"
    date_text = unix_to_local(int(doc.get("date") or 0), timezone_name).replace(" ", ", ")
    currency = doc.get("currency") or {}
    currency_code = str(currency.get("code_chr") or "UZS")
    amount = float(doc.get("amount") or 0)

    return "\n".join(
        [
            f"Ulgurji vozvrat #{code}",
            f"Mijoz: {partner_name}",
            f"Sana: {date_text}",
            f"Jami: {_format_amount_text(amount)} {currency_code}",
        ]
    )


def build_wholesale_order_caption(
    *,
    doc: dict[str, Any],
    timezone_name: str,
) -> str:
    code = doc.get("code") or f"ID-{doc.get('id', '-')}"
    partner = doc.get("partner") or {}
    partner_name = partner.get("name") or partner.get("full_name") or "Noma'lum"
    date_text = unix_to_local(int(doc.get("date") or 0), timezone_name).replace(" ", ", ")
    currency = doc.get("currency") or {}
    currency_code = str(currency.get("code_chr") or "UZS")
    amount = float(doc.get("amount") or 0)
    status_name = str((doc.get("status") or {}).get("name") or "-")

    return "\n".join(
        [
            f"Ulgurji zakaz #{code}",
            f"Mijoz: {partner_name}",
            f"Sana: {date_text}",
            f"Status: {status_name}",
            f"Jami: {_format_amount_text(amount)} {currency_code}",
        ]
    )


def build_retail_sale_caption(
    *,
    cheque: dict[str, Any],
    total_debt: float,
    timezone_name: str,
) -> str:
    code = cheque.get("code") or f"ID-{cheque.get('uuid', '-')}"
    customer = ((cheque.get("card") or {}).get("customer") or {})
    customer_name = _customer_name(customer)
    date_text = unix_to_local(int(cheque.get("date") or 0), timezone_name).replace(" ", ", ")
    amount = float(cheque.get("amount") or 0)

    return "\n".join(
        [
            f"Yangi chek #{code}",
            f"Mijoz: {customer_name}",
            f"Sana: {date_text}",
            f"Jami: {format_money(amount)} UZS",
            f"Qarz: {format_money(total_debt)} UZS",
        ]
    )


def build_retail_payment_caption(
    *,
    cheque: dict[str, Any],
    timezone_name: str,
) -> str:
    code = cheque.get("code") or f"ID-{cheque.get('uuid', '-')}"
    customer = ((cheque.get("card") or {}).get("customer") or {})
    customer_name = _customer_name(customer)
    date_text = unix_to_local(int(cheque.get("date") or 0), timezone_name).replace(" ", ", ")
    amount = float(cheque.get("amount") or 0)

    return "\n".join(
        [
            f"Chakana to'lov #{code}",
            f"Mijoz: {customer_name}",
            f"Sana: {date_text}",
            f"To'lov: {format_money(amount)} UZS",
        ]
    )
