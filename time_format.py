from __future__ import annotations

import datetime as dt
import re

TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")

MAX_MINUTES_PER_DAY = 24 * 60

TIME_INPUT_HINT = "Формат: <b>ЧЧ:ММ</b>\nПример: <code>7:30</code>"

REST_INPUT_HINT = (
    "😴 Или отправьте <b>отдых</b> — день будет отмечен как день отдыха."
)

BREAKTHROUGH_INPUT_HINT = (
    "⭐ Или отправьте <b>прорыв</b> — день будет отмечен как день прорыва."
)

REST_KEYWORD = "отдых"
BREAKTHROUGH_KEYWORD = "прорыв"

DATE_PATTERN = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
DATE_INPUT_HINT = "Формат: <b>ДД.ММ.ГГГГ</b>\nПример: <code>15.05.2026</code>"


def parse_rest_input(text: str) -> bool:
    return text.strip().casefold() == REST_KEYWORD.casefold()


def parse_breakthrough_input(text: str) -> bool:
    return text.strip().casefold() == BREAKTHROUGH_KEYWORD.casefold()


def parse_time_input(text: str) -> tuple[int, int] | None:
    """Разбирает строку ЧЧ:ММ. Возвращает (часы, минуты) или None."""
    match = TIME_PATTERN.match(text.strip())
    if not match:
        return None

    hours, minutes = int(match.group(1)), int(match.group(2))
    if minutes >= 60:
        return None
    if hours == 0 and minutes == 0:
        return None
    if hours * 60 + minutes > MAX_MINUTES_PER_DAY:
        return None
    return hours, minutes


def duration_to_hours(hours: int, minutes: int) -> float:
    return hours + minutes / 60


def format_duration(hours: float) -> str:
    """Человекочитаемый вид: 2ч 30м."""
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    if h and m:
        return f"{h}ч {m}м"
    if h:
        return f"{h}ч"
    return f"{m}м"


def parse_date_input(text: str) -> dt.date | None:
    match = DATE_PATTERN.match(text.strip())
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def format_duration_clock(hours: float) -> str:
    """Вид ЧЧ:ММ для подсказок."""
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    return f"{h}:{m:02d}"
