from __future__ import annotations

import datetime as dt
from html import escape

from database import get_breakthroughs_for_year, get_display_name, get_user_stats
from access import display_name_for
from time_format import format_duration
from ui_branding import (
    CUSTOM_EMOJI_BREAKTHROUGH,
    PLACEHOLDER_BREAKTHROUGH,
    tg_emoji,
)


async def format_user_stats(user_id: int, heading: str | None = None) -> str:
    stats = await get_user_stats(user_id)
    name = display_name_for(user_id, await get_display_name(user_id) or f"ID {user_id}")
    header = heading if heading is not None else name
    best = stats["best_day"]
    streak = int(stats["streak"])

    streak_line = f"Серия продуктивных дней: <b>{streak}</b>\n"

    return (
        f"<b>{header}</b>\n"
        f"Всего часов: <b>{format_duration(stats['total_hours'])}</b>\n"
        f"Продуктивных дней: <b>{stats['productive_days']}</b>\n"
        f"{streak_line}"
        f"В среднем в день уделяется <b>{format_duration(stats['avg_daily'])}</b>\n"
        f"Рекорд за день: <b>{format_duration(best) if best > 0 else '—'}</b>"
    )


async def format_breakthroughs_list(year: int) -> str:
    rows = await get_breakthroughs_for_year(year)
    header = (
        f"{tg_emoji(CUSTOM_EMOJI_BREAKTHROUGH, PLACEHOLDER_BREAKTHROUGH)} "
        f"<b>Прорывы — {year}</b>\n"
    )
    if not rows:
        return (
            f"{header}\n"
            "Пока нет отмеченных прорывов.\n"
            "Отметьте день словом <b>прорыв</b> и опишите его."
        )

    by_user: dict[tuple[int, str], list[tuple[dt.date, str]]] = {}
    for user_id, name, entry_date, note in rows:
        display = display_name_for(user_id, await get_display_name(user_id) or name)
        by_user.setdefault((user_id, display), []).append((entry_date, note))

    blocks: list[str] = [header]
    for (_uid, display), days in by_user.items():
        blocks.append(f"<b>{escape(display)}</b>")
        for entry_date, note in days:
            date_label = entry_date.strftime("%d.%m.%Y")
            desc = escape(note.strip()) if note.strip() else "без описания"
            blocks.append(f"• {date_label} ({desc})")
        blocks.append("")

    return "\n".join(blocks).strip()


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
