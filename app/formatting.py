import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PHONE_RE = re.compile(r"\d+")


def normalize_phone(phone_raw: str) -> str:
    digits = "".join(PHONE_RE.findall(phone_raw or ""))
    if not digits:
        return ""
    if digits.startswith("998") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 9:
        return f"+998{digits}"
    if digits.startswith("+"):
        return phone_raw
    if len(digits) == 9:
        return f"+998{digits}"
    if not phone_raw.startswith("+"):
        return f"+{digits}"
    return phone_raw


def extract_first_phone(value: str) -> str:
    if not value:
        return ""
    parts = re.split(r"[;,/ ]+", value.strip())
    for part in parts:
        normalized = normalize_phone(part)
        if normalized:
            return normalized
    normalized_whole = normalize_phone(value)
    return normalized_whole


def format_money(amount: float) -> str:
    rounded = int(round(amount or 0))
    return f"{rounded:,}".replace(",", " ")


def unix_to_local(dt_unix: int, tz_name: str) -> str:
    if not dt_unix:
        return "-"
    utc_dt = datetime.fromtimestamp(dt_unix, tz=timezone.utc)
    try:
        target_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        # Tashkent has a stable UTC+5 offset, so we can safely fall back.
        if tz_name == "Asia/Tashkent":
            target_tz = timezone(timedelta(hours=5))
        else:
            target_tz = timezone.utc
    local_dt = utc_dt.astimezone(target_tz)
    return local_dt.strftime("%d.%m.%Y %H:%M")
