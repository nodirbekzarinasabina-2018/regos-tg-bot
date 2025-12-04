def format_num(value) -> str:
    try:
        return f"{float(value):,.0f}".replace(",", " ")
    except Exception:
        return str(value)


def format_sale(data: dict) -> str:
    lines = [
        "✅ SAVDO TASDIQLANDI",
        f"📄 Hujjat №: {data.get('doc_number', '')}",
        f"📅 Sana: {data.get('date', '')}",
        f"🏪 Ombor: {data.get('warehouse', '')}",
        ""
    ]

    for item in data.get("items", []):
        lines.append(
            f"• {item.get('name')} — {item.get('qty')} x {format_num(item.get('price'))}"
        )

    lines.append("")
    lines.append(f"💰 Jami: {format_num(data.get('total'))}")

    return "\n".join(lines)


def format_payment(data: dict) -> str:
    return "\n".join([
        "💳 TO‘LOV KELDI",
        f"📄 Hujjat №: {data.get('doc_number', '')}",
        f"📅 Sana: {data.get('date', '')}",
        f"💵 Summa: {format_num(data.get('amount'))}",
        f"👤 Kontragent: {data.get('partner', '')}",
    ])
