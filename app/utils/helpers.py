import re
from datetime import datetime


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""

    phone = re.sub(r"\D", "", phone)

    if phone.startswith("998") and len(phone) == 12:
        return phone

    if phone.startswith("9") and len(phone) == 9:
        return "998" + phone

    return phone


def ts_to_date(ts: int | str) -> str:
    try:
        ts = int(ts)
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""
