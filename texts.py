from __future__ import annotations

import datetime as dt

from database import get_display_name, get_user_stats
from time_format import format_duration


async def format_user_stats(user_id: int, heading: str | None = None) -> str:
    stats = await get_user_stats(user_id)
    name = await get_display_name(user_id) or f"ID {user_id}"
    header = heading if heading is not None else name
    best = stats["best_day"]
    streak = int(stats["streak"])

    streak_line = f"Серия продуктивных дней: <b>{streak}</b>\n"

    return (
        f"<b>{header}</b>\n"
        f"Всего часов: <b>{format_duration(stats['total_hours'])}</b>\n"
        f"Продуктивных дней: <b>{stats['productive_days']}</b>\n"
        f"{streak_line}"
        f"В этом месяце: <b>{format_duration(stats['month_hours'])}</b>\n"
        f"В среднем в день уделяется <b>{format_duration(stats['avg_daily'])}</b>\n"
        f"Рекорд за день: <b>{format_duration(best) if best > 0 else '—'}</b>"
    )


def format_day_detail(
    entry_date: dt.date,
    hours: float | None,
    owner_name: str,
    *,
    is_rest: bool = False,
) -> str:
    date_label = entry_date.strftime("%d.%m.%Y")
    if is_rest:
        return (
            f"<b>{owner_name}</b> · {date_label}\n"
            "Отмечен <b>день отдыха</b>."
        )
    if hours is None or hours <= 0:
        return (
            f"<b>{owner_name}</b> · {date_label}\n"
            "В этот день продуктивность не отмечена."
        )
    return (
        f"<b>{owner_name}</b> · {date_label}\n"
        f"Продуктивный день: <b>{format_duration(hours)}</b>"
    )
