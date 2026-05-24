from __future__ import annotations

import asyncio
import calendar
import datetime as dt
import io
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle

from database import (
    DayEntry,
    fill_missed_days_for_month,
    get_breakthroughs_for_year,
    get_display_name,
    get_month_entries,
    get_registered_users,
)
from keyboards import MONTH_NAMES
from time_format import format_duration, format_duration_clock

if TYPE_CHECKING:
    from aiogram.types import BufferedInputFile

USER_COLORS = ("#5B8DEF", "#E85D4E", "#3CB371", "#F4A460", "#9B59B6", "#1ABC9C")
EMPTY_COLOR = "#D8DEE9"
PRODUCTIVE_COLOR = "#5B8DEF"
HIGHLIGHT_COLOR = "#E85D4E"
# Мягкий шалфейно-мятный — ассоциация с отдыхом и восстановлением
REST_COLOR = "#73C6A8"
WEEKDAY_ABBR = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
WEEKDAY_LABEL_COLOR = "#222222"
WEEKEND_LABEL_COLOR = "#E85D4E"
BREAKTHROUGH_CELL_COLOR = "#FFF8E1"


def _entry_for_day(
    entries: dict[dt.date, DayEntry], day: dt.date
) -> DayEntry:
    return entries.get(day, DayEntry(0.0, False, False))


def _max_productive_hours(entries: list[DayEntry]) -> float:
    """Максимальная высота среди отмеченных продуктивных дней."""
    return max(
        (e.hours for e in entries if e.hours > 0 and not e.is_rest),
        default=0.0,
    )


def _bar_display_height(entry: DayEntry, *, rest_height: float) -> float:
    if entry.is_rest:
        return rest_height if rest_height > 0 else 1.0
    if entry.is_breakthrough and entry.hours <= 0:
        return rest_height if rest_height > 0 else 1.0
    return entry.hours


def _user_bar_color(base_color: str, entry: DayEntry) -> str | tuple:
    """Отдых — цвет восстановления; продуктивность/прорыв — цвет участника."""
    if entry.is_rest:
        return REST_COLOR
    if entry.is_breakthrough or entry.hours > 0:
        return base_color
    return mcolors.to_rgba(base_color, alpha=0.22)


def _day_bar_color(
    entry: DayEntry,
    *,
    highlight: bool = False,
) -> str:
    if highlight:
        return HIGHLIGHT_COLOR
    if entry.is_rest:
        return REST_COLOR
    if entry.hours > 0:
        return PRODUCTIVE_COLOR
    return EMPTY_COLOR


def _apply_day_axis_labels(ax, all_days: list[dt.date]) -> None:
    """Число дня на оси, под ним день недели, ниже — подпись оси."""
    day_numbers = [day.day for day in all_days]
    ax.set_xticks(day_numbers)
    ax.set_xticklabels(day_numbers, fontsize=8, color=WEEKDAY_LABEL_COLOR)
    ax.tick_params(axis="x", pad=2)

    for day_num, day_date in zip(day_numbers, all_days):
        weekday = day_date.weekday()
        color = WEEKEND_LABEL_COLOR if weekday >= 5 else WEEKDAY_LABEL_COLOR
        ax.text(
            day_num,
            -0.06,
            WEEKDAY_ABBR[weekday],
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=7,
            color=color,
            clip_on=False,
        )

    ax.text(
        0.5,
        -0.16,
        "День месяца",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=11,
        color=WEEKDAY_LABEL_COLOR,
        clip_on=False,
    )


def _render_single_chart(
    entries: dict[dt.date, DayEntry],
    title: str,
    year: int,
    month: int,
    highlight: dt.date | None,
) -> bytes:
    _, last_day = calendar.monthrange(year, month)
    all_days = [dt.date(year, month, day) for day in range(1, last_day + 1)]
    day_entries = [_entry_for_day(entries, day) for day in all_days]
    total_month = sum(e.hours for e in day_entries)
    rest_height = _max_productive_hours(day_entries)
    values = [_bar_display_height(e, rest_height=rest_height) for e in day_entries]
    max_value = max(values) if values else 1.0

    fig, ax = plt.subplots(figsize=(max(12, last_day * 0.38), 5.5))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    day_numbers = list(range(1, last_day + 1))
    colors = [
        _day_bar_color(
            day_entries[i],
            highlight=bool(highlight and day == highlight),
        )
        for i, day in enumerate(all_days)
    ]

    bars = ax.bar(day_numbers, values, color=colors, width=0.72, edgecolor="white")
    ax.set_ylabel("Время (часы)", fontsize=11)
    ax.set_xlim(0.4, last_day + 0.6)
    _apply_day_axis_labels(ax, all_days)
    ax.set_ylim(0, max(max_value * 1.3, 1.0))
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    for bar, day, entry in zip(bars, all_days, day_entries):
        if entry.is_rest or entry.hours <= 0:
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            format_duration_clock(entry.hours),
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color="#222222",
        )

    legend_handles = [
        Patch(facecolor=PRODUCTIVE_COLOR, edgecolor="white", label="продуктивность"),
        Patch(facecolor=REST_COLOR, edgecolor="white", label="отдых"),
        Patch(facecolor=EMPTY_COLOR, edgecolor="white", label="нет записи"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8, framealpha=0.9)

    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    month_total = (
        f"Итого за месяц: {format_duration(total_month)}"
        if total_month > 0
        else "Итого за месяц: 0ч"
    )
    fig.text(0.5, 0.02, month_total, ha="center", fontsize=10, color="#444444")

    buf = io.BytesIO()
    plt.tight_layout(rect=[0, 0.11, 1, 1])
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _render_team_chart(
    users_series: list[tuple[str, dict[dt.date, DayEntry]]],
    title: str,
    year: int,
    month: int,
) -> bytes:
    _, last_day = calendar.monthrange(year, month)
    all_days = [dt.date(year, month, day) for day in range(1, last_day + 1)]
    day_numbers = np.arange(1, last_day + 1)
    n_users = len(users_series)

    fig, ax = plt.subplots(figsize=(max(12, last_day * 0.42), 6))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    group_width = 0.82
    bar_width = group_width / max(n_users, 1)

    all_day_entries = [
        [_entry_for_day(entries, day) for day in all_days]
        for _name, entries in users_series
    ]
    max_value = 0.0

    for idx, (name, entries) in enumerate(users_series):
        day_entries = all_day_entries[idx]
        rest_height = _max_productive_hours(day_entries)
        values = [_bar_display_height(e, rest_height=rest_height) for e in day_entries]
        max_value = max(max_value, max(values) if values else 0.0)
        offset = (idx - (n_users - 1) / 2) * bar_width
        x = day_numbers + offset
        base_color = USER_COLORS[idx % len(USER_COLORS)]

        bar_colors = [_user_bar_color(base_color, e) for e in day_entries]

        bars = ax.bar(
            x,
            values,
            width=bar_width * 0.92,
            color=bar_colors,
            edgecolor="white",
            linewidth=0.6,
        )

        for bar, entry in zip(bars, day_entries):
            cx = bar.get_x() + bar.get_width() / 2
            if entry.is_breakthrough:
                ax.text(
                    cx,
                    bar.get_height(),
                    "★",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color=base_color,
                )
            if entry.is_rest or entry.hours <= 0:
                continue
            label_y = bar.get_height() * 0.45 if entry.is_breakthrough else bar.get_height()
            label_va = "center" if entry.is_breakthrough else "bottom"
            ax.text(
                cx,
                label_y,
                format_duration_clock(entry.hours),
                ha="center",
                va=label_va,
                fontsize=7,
                fontweight="bold",
                color="#222222",
            )

    ax.set_ylabel("Время (часы)", fontsize=11)
    ax.set_xlim(0.4, last_day + 0.6)
    _apply_day_axis_labels(ax, all_days)
    y_top = max(max_value * 1.35, 1.0)
    ax.set_ylim(0, y_top)
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    user_handles = [
        Patch(
            facecolor=USER_COLORS[idx % len(USER_COLORS)],
            edgecolor=USER_COLORS[idx % len(USER_COLORS)],
            label=name,
        )
        for idx, (name, _) in enumerate(users_series)
    ]
    rest_handle = Patch(facecolor=REST_COLOR, edgecolor=REST_COLOR, label="отдых")
    ax.legend(
        handles=user_handles + [rest_handle],
        loc="upper right",
        fontsize=9,
        framealpha=0.9,
    )
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)

    totals = [
        f"{name}: {format_duration(sum(_entry_for_day(entries, d).hours for d in all_days))}"
        for name, entries in users_series
    ]
    fig.text(0.5, 0.02, " · ".join(totals), ha="center", fontsize=9, color="#444444")

    buf = io.BytesIO()
    plt.tight_layout(rect=[0, 0.12, 1, 1])
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _draw_month_breakthrough_calendar(
    ax,
    year: int,
    month: int,
    users_series: list[tuple[str, str, set[dt.date]]],
) -> None:
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 7)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title(MONTH_NAMES[month], fontsize=14, fontweight="bold", pad=8)

    for col, abbr in enumerate(WEEKDAY_ABBR):
        wd_color = WEEKEND_LABEL_COLOR if col >= 5 else WEEKDAY_LABEL_COLOR
        ax.text(
            col + 0.5,
            0.35,
            abbr,
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=wd_color,
        )

    cal = calendar.Calendar(firstweekday=0)
    for week_idx, week in enumerate(cal.monthdayscalendar(year, month)):
        for col, day in enumerate(week):
            if day == 0:
                continue
            row = week_idx + 1
            day_date = dt.date(year, month, day)
            marked = [
                (name, color)
                for name, color, dates in users_series
                if day_date in dates
            ]

            ax.add_patch(
                Rectangle(
                    (col, row),
                    1,
                    1,
                    facecolor=BREAKTHROUGH_CELL_COLOR if marked else "#FFFFFF",
                    edgecolor="#C8C8C8",
                    linewidth=1.0,
                )
            )

            day_color = WEEKEND_LABEL_COLOR if col >= 5 else WEEKDAY_LABEL_COLOR
            ax.text(
                col + 0.5,
                row + 0.38,
                str(day),
                ha="center",
                va="center",
                fontsize=11,
                fontweight="bold",
                color=day_color,
            )

            for star_idx, (_name, color) in enumerate(marked):
                offset = (star_idx - (len(marked) - 1) / 2) * 0.24
                ax.text(
                    col + 0.5 + offset,
                    row + 0.72,
                    "★",
                    ha="center",
                    va="center",
                    fontsize=10,
                    fontweight="bold",
                    color=color,
                )


def _render_year_breakthrough_calendar(
    year: int,
    users_series: list[tuple[str, str, set[dt.date]]],
) -> bytes:
    fig, axes = plt.subplots(4, 3, figsize=(22, 28))
    fig.patch.set_facecolor("#FAFAFA")

    total_days = sum(len(dates) for _n, _c, dates in users_series)
    fig.suptitle(
        f"Календарь прорывных дней — {year}",
        fontsize=22,
        fontweight="bold",
        y=0.985,
    )

    for month in range(1, 13):
        ax = axes[(month - 1) // 3, (month - 1) % 3]
        ax.set_facecolor("#FAFAFA")
        _draw_month_breakthrough_calendar(ax, year, month, users_series)

    if users_series:
        legend_handles = [
            Patch(facecolor=color, edgecolor=color, label=name)
            for name, color, _dates in users_series
            if _dates
        ]
        if not legend_handles:
            legend_handles = [
                Patch(facecolor=color, edgecolor=color, label=name)
                for name, color, _dates in users_series
            ]
        fig.legend(
            handles=legend_handles,
            loc="lower center",
            ncol=min(len(legend_handles), 3),
            fontsize=12,
            framealpha=0.9,
            bbox_to_anchor=(0.5, 0.015),
        )
    else:
        fig.text(
            0.5,
            0.02,
            "Прорывных дней за год пока нет",
            ha="center",
            fontsize=13,
            color="#666666",
        )

    subtitle = (
        f"Всего прорывных дней: {total_days}"
        if total_days
        else "Отметьте прорыв через «✅отметить» — слово «прорыв»"
    )
    fig.text(0.5, 0.045, subtitle, ha="center", fontsize=12, color="#444444")

    buf = io.BytesIO()
    plt.tight_layout(rect=[0, 0.07, 1, 0.965], h_pad=2.8, w_pad=1.8)
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


async def _load_users_breakthrough_series(
    year: int,
) -> list[tuple[str, str, set[dt.date]]]:
    users = await get_registered_users()
    dates_by_user: dict[int, set[dt.date]] = {uid: set() for uid, _ in users}

    for user_id, _name, entry_date in await get_breakthroughs_for_year(year):
        if user_id in dates_by_user:
            dates_by_user[user_id].add(entry_date)

    series: list[tuple[str, str, set[dt.date]]] = []
    for idx, (user_id, name) in enumerate(users):
        display = await get_display_name(user_id) or name
        dates = dates_by_user.get(user_id, set())
        color = USER_COLORS[idx % len(USER_COLORS)]
        series.append((display, color, dates))
    return series


async def build_breakthrough_year_calendar(year: int) -> tuple[bytes, str]:
    users_series = await _load_users_breakthrough_series(year)
    png = await asyncio.to_thread(
        _render_year_breakthrough_calendar, year, users_series
    )
    total = sum(len(dates) for _n, _c, dates in users_series)
    caption = f"⭐ <b>Календарь прорывов</b> · {year} · дней: <b>{total}</b>"
    return png, caption


async def _load_users_month_data(
    year: int, month: int,
) -> list[tuple[int, str, dict[dt.date, DayEntry]]]:
    result: list[tuple[int, str, dict[dt.date, DayEntry]]] = []
    for user_id, name in await get_registered_users():
        display = await get_display_name(user_id) or name
        await fill_missed_days_for_month(user_id, display, year, month)
        entries = await get_month_entries(user_id, year, month)
        result.append((user_id, display, entries))
    return result


async def build_team_progress_chart(year: int, month: int) -> tuple[bytes, str]:
    users_data = await _load_users_month_data(year, month)
    if not users_data:
        raise RuntimeError("Нет зарегистрированных участников")

    users_series = [(name, entries) for _, name, entries in users_data]
    title = f"Общий прогресс — {MONTH_NAMES[month]} {year}"
    png = await asyncio.to_thread(
        _render_team_chart, users_series, title, year, month
    )
    caption = f"📊 <b>Общий график</b> · {MONTH_NAMES[month]} {year}"
    return png, caption


async def build_progress_chart(
    user_id: int,
    year: int,
    month: int,
    *,
    highlight: dt.date | None = None,
) -> tuple[bytes, str]:
    """Один участник — для обратной совместимости."""
    name = await get_display_name(user_id) or f"ID {user_id}"
    await fill_missed_days_for_month(user_id, name, year, month)
    entries = await get_month_entries(user_id, year, month)
    title = f"{name} — {MONTH_NAMES[month]} {year}"
    png = await asyncio.to_thread(
        _render_single_chart, entries, title, year, month, highlight
    )

    if highlight and highlight in entries:
        day_label = highlight.strftime("%d.%m.%Y")
        entry = entries[highlight]
        if entry.is_rest:
            day_info = "<b>день отдыха</b>"
        elif entry.is_breakthrough:
            if entry.hours > 0:
                day_info = (
                    f"<b>день прорыва</b> ⭐ · <b>{format_duration(entry.hours)}</b> "
                    f"(<code>{format_duration_clock(entry.hours)}</code>)"
                )
            else:
                day_info = "<b>день прорыва</b> ⭐"
        else:
            day_info = (
                f"<b>{format_duration(entry.hours)}</b> "
                f"(<code>{format_duration_clock(entry.hours)}</code>)"
            )
        caption = (
            f"📊 <b>{name}</b> · {MONTH_NAMES[month]} {year}\n"
            f"Отмечено {day_label}: {day_info}"
        )
    else:
        caption = f"📊 <b>{name}</b> · {MONTH_NAMES[month]} {year}"

    return png, caption


def chart_photo(png: bytes, filename: str = "progress.png") -> BufferedInputFile:
    from aiogram.types import BufferedInputFile

    return BufferedInputFile(png, filename=filename)
